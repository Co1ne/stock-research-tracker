from datetime import date, datetime, timedelta
import json
from traceback import format_exc

from sqlalchemy.orm import Session

from app.core.config import settings
from app.data_sources.base import DataSourceResult
from app.data_sources.registry import DataSourceRegistry
from app.models.models import Announcement, BusinessLine, BusinessLineEvidence, Company, FinancialSnapshot, IngestionRun, NewsItem, RiskEvent
from app.services.business_line_matcher import match_business_lines
from app.services.classification_service import classify_text
from app.services.evidence_rule_service import EvidenceRuleService
from app.services.fetch_utils import content_hash, importance_score
from app.services.risk_rule_service import detect_risk


INGESTION_TYPES = {'announcement', 'news', 'financial'}


class IngestionService:
    def __init__(self, db: Session, registry: DataSourceRegistry | None = None):
        self.db = db
        self.registry = registry or DataSourceRegistry(db)

    def ingest_company_all(self, company_id: int, force: bool = False):
        return self.ingest_company(company_id, ['announcement', 'news', 'financial'], force)

    def ingest_company(self, company_id: int, types: list[str] | None = None, force: bool = False):
        company = self.db.get(Company, company_id)
        if not company:
            return None
        normalized = self._normalize_types(types)
        result = {'company_id': company.id, 'company_name': company.name, 'status': 'success', 'runs': []}
        any_failed = False
        any_success = False
        for source_type in normalized:
            type_runs = self._ingest_one_type(company, source_type, force)
            result['runs'].extend(type_runs)
            any_failed = any_failed or any(run['status'] == 'failed' for run in type_runs)
            any_success = any_success or any(run['status'] in {'success', 'partial_success'} for run in type_runs)
        if any_failed and any_success:
            result['status'] = 'partial_success'
        elif any_failed:
            result['status'] = 'failed'
        return result

    def _normalize_types(self, types: list[str] | None):
        if not types or 'all' in types:
            return ['announcement', 'news', 'financial']
        normalized = []
        for item in types:
            value = str(item or '').strip()
            if value == 'announcements':
                value = 'announcement'
            if value == 'financials':
                value = 'financial'
            if value not in INGESTION_TYPES:
                raise ValueError(f'unsupported ingestion type: {value}')
            if value not in normalized:
                normalized.append(value)
        return normalized

    def _ingest_one_type(self, company: Company, source_type: str, force: bool):
        runs = []
        for adapter in self.registry.ordered_adapters():
            run = self._start_run(company, adapter.name, source_type, {'force': force})
            try:
                result = self._fetch(adapter, source_type, company)
                if not result.ok:
                    self._finish_run(run, 'failed', result, result.error.message, result.error.raw_error)
                    runs.append(_ingestion_run_out(run, self.db))
                    continue
                stats = self._persist_result(company, source_type, adapter.name, result, run.id, force)
                result.result_summary = {**(result.result_summary or {}), **stats}
                self._finish_run(run, 'success', result)
                runs.append(_ingestion_run_out(run, self.db))
                break
            except Exception as exc:
                self.db.rollback()
                run = self.db.merge(run)
                self._finish_run(run, 'failed', DataSourceResult(adapter.name, source_type), str(exc), format_exc())
                runs.append(_ingestion_run_out(run, self.db))
                continue
        return runs

    def _fetch(self, adapter, source_type: str, company: Company):
        if source_type == 'announcement':
            end = date.today()
            start = end - timedelta(days=settings.fetch_lookback_days_announcement)
            return adapter.fetch_announcements(company, start, end)
        if source_type == 'news':
            lines = self.db.query(BusinessLine).filter(BusinessLine.company_id == company.id).all()
            keywords = self._keywords(company, lines)
            return adapter.fetch_news(company, keywords, settings.fetch_max_news_per_company)
        if source_type == 'financial':
            return adapter.fetch_financials(company)
        raise ValueError(f'unsupported ingestion type: {source_type}')

    def _persist_result(self, company: Company, source_type: str, source_name: str, result: DataSourceResult, run_id: int, force: bool):
        if source_type == 'announcement':
            return self._persist_announcements(company, source_name, result.items, run_id, force)
        if source_type == 'news':
            return self._persist_news(company, source_name, result.items, run_id, force)
        if source_type == 'financial':
            return self._persist_financials(company, source_name, result.items, run_id)
        raise ValueError(f'unsupported ingestion type: {source_type}')

    def _persist_announcements(self, company: Company, source_name: str, items: list, run_id: int, force: bool):
        stats = {'items_found': len(items), 'items_created': 0, 'items_updated': 0, 'duplicated': 0, 'evidence_created': 0}
        lines = self.db.query(BusinessLine).filter(BusinessLine.company_id == company.id).all()
        line_payload = [{'name': line.name, 'keywords': line.keywords or []} for line in lines]
        for dto in items:
            digest = content_hash(company.id, dto.title, dto.publish_time, source_name, dto.url)
            existing = self.db.query(Announcement).filter(Announcement.company_id == company.id, Announcement.title == dto.title, Announcement.publish_time == dto.publish_time).first()
            if not existing and dto.url:
                existing = self.db.query(Announcement).filter(Announcement.company_id == company.id, Announcement.url == dto.url).first()
            if existing and not force:
                existing.source_name = existing.source_name or source_name
                existing.ingestion_run_id = run_id
                existing.raw_payload = existing.raw_payload or _safe_extra(dto.extra)
                self._tag_source_evidence('announcement', existing.id, existing.source_name, run_id, existing.raw_payload)
                stats['duplicated'] += 1
                continue
            text = f'{dto.title} {dto.summary or ""} {dto.raw_text or ""}'
            matched = match_business_lines(text, line_payload)
            risk, level = detect_risk(text)
            item = existing or Announcement(company_id=company.id, title=dto.title, publish_time=dto.publish_time)
            item.source = dto.source
            item.source_name = source_name
            item.url = dto.url
            item.category = classify_text(text)
            item.importance_score = importance_score(risk, bool(matched), 3)
            item.is_risk_event = risk
            item.is_business_update = bool(matched)
            item.related_business_lines = matched
            item.need_manual_review = True
            item.summary = dto.summary
            item.raw_text = dto.raw_text
            item.content_hash = item.content_hash or digest
            item.ingestion_run_id = run_id
            item.raw_payload = _safe_extra(dto.extra)
            self.db.add(item)
            self.db.flush()
            if risk:
                risk_event = self._get_or_create_risk(company, 'announcement', item.id, dto.title, level, (dto.summary or dto.raw_text or '')[:200])
                stats['evidence_created'] += EvidenceRuleService(self.db).create_from_risk_event(risk_event)
            else:
                stats['evidence_created'] += EvidenceRuleService(self.db).create_from_source_item('announcement', item)
            self._tag_source_evidence('announcement', item.id, source_name, run_id, item.raw_payload)
            if existing:
                stats['items_updated'] += 1
            else:
                stats['items_created'] += 1
        self.db.commit()
        return stats

    def _persist_news(self, company: Company, source_name: str, items: list, run_id: int, force: bool):
        stats = {'items_found': len(items), 'items_created': 0, 'items_updated': 0, 'duplicated': 0, 'skipped_irrelevant': 0, 'evidence_created': 0}
        lines = self.db.query(BusinessLine).filter(BusinessLine.company_id == company.id).all()
        keywords = self._keywords(company, lines)
        line_payload = [{'name': line.name, 'keywords': line.keywords or []} for line in lines]
        cutoff = date.today() - timedelta(days=settings.fetch_lookback_days_news)
        for dto in items[:settings.fetch_max_news_per_company]:
            if dto.publish_time.date() < cutoff and source_name != 'local':
                continue
            text = f'{dto.title} {dto.summary or ""} {dto.raw_text or ""}'
            if not self._is_relevant(dto, company, keywords):
                stats['skipped_irrelevant'] += 1
                continue
            digest = content_hash(company.id, dto.title, dto.publish_time, source_name, dto.url)
            existing = self.db.query(NewsItem).filter(NewsItem.company_id == company.id, NewsItem.title == dto.title, NewsItem.publish_time == dto.publish_time).first()
            if not existing and dto.url:
                existing = self.db.query(NewsItem).filter(NewsItem.company_id == company.id, NewsItem.url == dto.url).first()
            if existing and not force:
                existing.source_name = existing.source_name or source_name
                existing.ingestion_run_id = run_id
                existing.raw_payload = existing.raw_payload or _safe_extra(dto.extra)
                self._tag_source_evidence('news', existing.id, existing.source_name, run_id, existing.raw_payload)
                stats['duplicated'] += 1
                continue
            matched = match_business_lines(text, line_payload)
            risk, level = detect_risk(text)
            item = existing or NewsItem(company_id=company.id, title=dto.title, publish_time=dto.publish_time)
            item.source = dto.source
            item.source_name = source_name
            item.url = dto.url
            item.category = classify_text(text)
            item.importance_score = importance_score(risk, bool(matched), 3)
            item.is_risk_event = risk
            item.is_business_update = bool(matched)
            item.related_business_lines = matched
            item.need_manual_review = True
            item.summary = dto.summary
            item.raw_text = dto.raw_text
            item.content_hash = item.content_hash or digest
            item.ingestion_run_id = run_id
            item.raw_payload = _safe_extra(dto.extra)
            self.db.add(item)
            self.db.flush()
            if risk:
                risk_event = self._get_or_create_risk(company, 'news', item.id, dto.title, level, (dto.summary or dto.raw_text or '')[:200])
                stats['evidence_created'] += EvidenceRuleService(self.db).create_from_risk_event(risk_event)
            else:
                stats['evidence_created'] += EvidenceRuleService(self.db).create_from_source_item('news', item)
            self._tag_source_evidence('news', item.id, source_name, run_id, item.raw_payload)
            if existing:
                stats['items_updated'] += 1
            else:
                stats['items_created'] += 1
        self.db.commit()
        return stats

    def _persist_financials(self, company: Company, source_name: str, items: list, run_id: int):
        stats = {'items_found': len(items), 'items_created': 0, 'items_updated': 0, 'risk_created': 0}
        for dto in items:
            row = self.db.query(FinancialSnapshot).filter(FinancialSnapshot.company_id == company.id, FinancialSnapshot.report_period == dto.report_period).first()
            created = row is None
            if not row:
                row = FinancialSnapshot(company_id=company.id, stock_code=company.code, report_period=dto.report_period)
                self.db.add(row)
            row.revenue = dto.revenue
            row.net_profit = dto.net_profit
            row.net_profit_deducted = dto.net_profit_deducted
            row.gross_margin = dto.gross_margin
            row.net_margin = dto.net_margin
            row.operating_cash_flow = dto.operating_cash_flow
            row.accounts_receivable = dto.accounts_receivable
            row.inventory = dto.inventory
            row.debt_asset_ratio = dto.debt_asset_ratio
            row.roe = dto.roe
            row.source = dto.source
            row.source_name = source_name
            row.raw_data = dto.raw_data
            row.ingestion_run_id = run_id
            self.db.flush()
            stats['items_created' if created else 'items_updated'] += 1
            stats['risk_created'] += self._detect_financial_risk(company, row)
        self.db.commit()
        return stats

    def _detect_financial_risk(self, company: Company, row: FinancialSnapshot):
        created = 0
        if row.operating_cash_flow is not None and row.net_profit is not None and row.operating_cash_flow < 0 < row.net_profit:
            risk = self._get_or_create_risk(company, 'financial', row.id, f'{company.name} 经营现金流与净利润背离', 'medium', f'{row.report_period} 经营现金流为负但净利润为正')
            created += EvidenceRuleService(self.db).create_from_risk_event(risk)
        if row.net_profit is not None and row.net_profit < 0:
            risk = self._get_or_create_risk(company, 'financial', row.id, f'{company.name} 归母净利润亏损', 'high', f'{row.report_period} 归母净利润为负')
            created += EvidenceRuleService(self.db).create_from_risk_event(risk)
        self._tag_source_evidence('financial', row.id, row.source_name or row.source or 'unknown', row.ingestion_run_id, row.raw_data)
        return created

    def _get_or_create_risk(self, company: Company, source_type: str, source_id: int, title: str, level: str, description: str):
        risk = self.db.query(RiskEvent).filter(RiskEvent.company_id == company.id, RiskEvent.source_type == source_type, RiskEvent.source_id == source_id, RiskEvent.title == title).first()
        if not risk:
            risk = RiskEvent(company_id=company.id, event_type='ingestion_rule', level=level, title=title, description=description, evidence='ingestion_rule', source_type=source_type, source_id=source_id)
            self.db.add(risk)
            self.db.flush()
        return risk

    def _tag_source_evidence(self, source_type: str, source_id: int, source_name: str, run_id: int | None, raw_payload: dict | None):
        rows = self.db.query(BusinessLineEvidence).filter(BusinessLineEvidence.source_type == source_type, BusinessLineEvidence.source_id == source_id).all()
        for row in rows:
            row.source_name = source_name
            row.ingestion_run_id = run_id
            row.raw_payload = raw_payload
            row.content_hash = row.content_hash or content_hash(row.company_id, row.source_type, row.source_id, row.title)
            row.review_status = row.review_status or 'pending'

    def _keywords(self, company: Company, lines: list[BusinessLine]):
        result = [company.name, company.code]
        for line in lines:
            result.extend(line.keywords or [])
        return [x for x in dict.fromkeys(result) if x]

    def _is_relevant(self, dto, company: Company, keywords: list[str]):
        text = f'{dto.title or ""} {dto.summary or ""} {dto.raw_text or ""}'
        if company.name in text or company.code in text or dto.related_company == company.name:
            return True
        business_keywords = [keyword for keyword in keywords[2:] if keyword and len(keyword) >= 4]
        return any(keyword in text for keyword in business_keywords)

    def _start_run(self, company: Company, source_name: str, source_type: str, request_params: dict):
        run = IngestionRun(company_id=company.id, source_name=source_name, source_type=source_type, status='success', started_at=datetime.utcnow(), request_params=request_params)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def _finish_run(self, run: IngestionRun, status: str, result: DataSourceResult, error_message: str | None = None, raw_error: str | None = None):
        finished = datetime.utcnow()
        run.status = status
        run.finished_at = finished
        run.duration_ms = int((finished - run.started_at).total_seconds() * 1000) if run.started_at else None
        run.items_found = len(result.items or [])
        run.items_created = (result.result_summary or {}).get('items_created', 0)
        run.items_updated = (result.result_summary or {}).get('items_updated', 0)
        run.error_message = error_message
        run.raw_error = raw_error
        run.request_params = {**(run.request_params or {}), **(result.request_params or {})}
        run.result_summary = result.result_summary or {}
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)


def _safe_extra(value):
    if not isinstance(value, dict):
        return {}
    try:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except TypeError:
        return {str(key): str(val) for key, val in value.items()}


def _ingestion_run_out(item: IngestionRun, db: Session):
    company = db.get(Company, item.company_id) if item.company_id else None
    return {
        'id': item.id,
        'company_id': item.company_id,
        'company_name': company.name if company else None,
        'stock_code': company.code if company else None,
        'source_name': item.source_name,
        'source_type': item.source_type,
        'status': item.status,
        'started_at': item.started_at,
        'finished_at': item.finished_at,
        'duration_ms': item.duration_ms,
        'items_found': item.items_found,
        'items_created': item.items_created,
        'items_updated': item.items_updated,
        'error_message': item.error_message,
        'raw_error': item.raw_error,
        'request_params': item.request_params,
        'result_summary': item.result_summary,
        'created_at': item.created_at,
    }
