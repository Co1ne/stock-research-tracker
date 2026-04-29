from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.data_sources.factory import news_provider
from app.models.models import BusinessLine, Company, NewsItem, RiskEvent
from app.services.business_line_evidence_service import BusinessLineEvidenceService
from app.services.business_line_matcher import match_business_lines
from app.services.classification_service import classify_text
from app.services.evidence_rule_service import EvidenceRuleService
from app.services.fetch_utils import content_hash, importance_score
from app.services.job_run_service import JobRunService
from app.services.logic_impact_service import LogicImpactService
from app.services.risk_rule_service import detect_risk


class NewsFetchService:
    def __init__(self, db: Session, provider=None):
        self.db = db
        self.provider = provider or news_provider()

    def _companies(self, company_id: int | None):
        q = self.db.query(Company).filter(Company.status != 'removed')
        if company_id:
            q = q.filter(Company.id == company_id)
        return q.order_by(Company.id.asc()).all()

    def _keywords(self, company: Company, lines: list[BusinessLine]):
        result = [company.name, company.code]
        for line in lines:
            result.extend(line.keywords or [])
        return [x for x in dict.fromkeys(result) if x]

    def _business_keywords(self, keywords: list[str]):
        generic = {'主营业务', '业务', '产品', '公司', '项目', '收入', '销售', '服务', '平台', '系统', '智能', '新能源'}
        return [keyword for keyword in keywords[2:] if keyword and keyword not in generic and len(keyword) >= 4]

    def _is_relevant(self, dto, company: Company, keywords: list[str]) -> tuple[bool, bool]:
        title = dto.title or ''
        text = f"{dto.title or ''} {dto.summary or ''} {dto.raw_text or ''}"
        if company.name in text or company.code in text or dto.related_company == company.name:
            return True, False
        if any(keyword in text for keyword in self._business_keywords(keywords)):
            return True, True
        return False, False

    def fetch(self, company_id: int | None = None, days: int | None = None, limit: int | None = None, record_job: bool = True):
        run = JobRunService(self.db).start('fetch_news') if record_job else None
        max_items = limit or settings.fetch_max_news_per_company
        cutoff = date.today() - timedelta(days=days or settings.fetch_lookback_days_news)
        result = {'fetched_companies': 0, 'fetched_items': 0, 'inserted': 0, 'duplicated': 0, 'skipped_irrelevant': 0, 'failed_companies': []}
        try:
            for company in self._companies(company_id):
                result['fetched_companies'] += 1
                try:
                    lines = self.db.query(BusinessLine).filter(BusinessLine.company_id == company.id).all()
                    keywords = self._keywords(company, lines)
                    dtos = self.provider.fetch_company_news(company, keywords, max_items)
                    result['fetched_items'] += len(dtos)
                    line_payload = [{'name': line.name, 'keywords': line.keywords or []} for line in lines]
                    for dto in dtos[:max_items]:
                        if dto.publish_time.date() < cutoff:
                            continue
                        relevant, uncertain = self._is_relevant(dto, company, keywords)
                        if not relevant:
                            result['skipped_irrelevant'] += 1
                            continue
                        digest = content_hash(company.id, dto.title, dto.publish_time, dto.url)
                        existing_query = self.db.query(NewsItem).filter(NewsItem.content_hash == digest)
                        if dto.url:
                            existing_query = existing_query.union(self.db.query(NewsItem).filter(NewsItem.url == dto.url))
                        existing = existing_query.first()
                        if existing:
                            result['duplicated'] += 1
                            continue
                        text = f"{dto.title} {dto.summary or ''} {dto.raw_text or ''}"
                        matched = match_business_lines(text, line_payload)
                        risk, level = detect_risk(text)
                        item = NewsItem(
                            title=dto.title,
                            source=dto.source,
                            url=dto.url,
                            publish_time=dto.publish_time,
                            company_id=company.id,
                            category=classify_text(text),
                            importance_score=importance_score(risk, bool(matched), 3),
                            is_risk_event=risk,
                            is_business_update=bool(matched),
                            related_business_lines=matched,
                            need_manual_review=risk or uncertain,
                            summary=dto.summary,
                            raw_text=dto.raw_text,
                            content_hash=digest,
                        )
                        self.db.add(item)
                        self.db.flush()
                        if risk:
                            risk_event = RiskEvent(company_id=company.id, event_type='rule_hit', level=level, title=dto.title, description=(dto.summary or dto.raw_text or '')[:200], evidence='rule', source_type='news', source_id=item.id)
                            self.db.add(risk_event)
                            self.db.flush()
                            EvidenceRuleService(self.db).create_from_risk_event(risk_event)
                        elif item.is_business_update or item.need_manual_review:
                            EvidenceRuleService(self.db).create_from_source_item('news', item)
                        result['inserted'] += 1
                        if settings.ai_auto_analyze_important_items and item.importance_score >= settings.ai_auto_analyze_importance_threshold:
                            LogicImpactService(self.db).analyze_news_logic(item.id)
                            BusinessLineEvidenceService(self.db).create_evidence_from_news(item.id)
                    self.db.commit()
                except Exception as exc:
                    self.db.rollback()
                    result['failed_companies'].append({'company': company.name, 'code': company.code, 'error': str(exc)})
            if run:
                JobRunService(self.db).success(run, result)
            return result
        except Exception as exc:
            if run:
                JobRunService(self.db).failed(run, str(exc), result)
            raise
