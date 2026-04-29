from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.data_sources.factory import announcement_provider
from app.models.models import Announcement, BusinessLine, Company, RiskEvent
from app.services.business_line_evidence_service import BusinessLineEvidenceService
from app.services.business_line_matcher import match_business_lines
from app.services.classification_service import classify_text
from app.services.evidence_rule_service import EvidenceRuleService
from app.services.fetch_utils import content_hash, importance_score
from app.services.job_run_service import JobRunService
from app.services.logic_impact_service import LogicImpactService
from app.services.risk_rule_service import detect_risk


class AnnouncementFetchService:
    def __init__(self, db: Session, provider=None):
        self.db = db
        self.provider = provider or announcement_provider()

    def _companies(self, company_id: int | None):
        q = self.db.query(Company).filter(Company.status != 'removed')
        if company_id:
            q = q.filter(Company.id == company_id)
        return q.order_by(Company.id.asc()).all()

    def fetch(self, company_id: int | None = None, days: int | None = None, limit: int | None = None, record_job: bool = True):
        run = JobRunService(self.db).start('fetch_announcements') if record_job else None
        result = {'fetched_companies': 0, 'fetched_items': 0, 'inserted': 0, 'duplicated': 0, 'failed_companies': []}
        try:
            lookback = days or settings.fetch_lookback_days_announcement
            start = date.today() - timedelta(days=lookback)
            end = date.today()
            for company in self._companies(company_id):
                result['fetched_companies'] += 1
                try:
                    items = self.provider.fetch_announcements(company.code, start, end)
                    if limit:
                        items = items[:limit]
                    result['fetched_items'] += len(items)
                    lines = self.db.query(BusinessLine).filter(BusinessLine.company_id == company.id).all()
                    line_payload = [{'name': line.name, 'keywords': line.keywords or []} for line in lines]
                    for dto in items:
                        digest = content_hash(company.id, dto.title, dto.publish_time, dto.url)
                        if self.db.query(Announcement).filter(Announcement.content_hash == digest).first():
                            result['duplicated'] += 1
                            continue
                        text = f"{dto.title} {dto.summary or ''} {dto.raw_text or ''}"
                        matched = match_business_lines(text, line_payload)
                        risk, level = detect_risk(text)
                        ann = Announcement(
                            company_id=company.id,
                            title=dto.title,
                            publish_time=dto.publish_time,
                            source=dto.source,
                            url=dto.url,
                            category=classify_text(text),
                            importance_score=importance_score(risk, bool(matched), 3),
                            is_risk_event=risk,
                            is_business_update=bool(matched),
                            related_business_lines=matched,
                            need_manual_review=risk,
                            summary=dto.summary,
                            raw_text=dto.raw_text,
                            content_hash=digest,
                        )
                        self.db.add(ann)
                        self.db.flush()
                        if risk:
                            risk_event = RiskEvent(company_id=company.id, event_type='rule_hit', level=level, title=dto.title, description=(dto.summary or dto.raw_text or '')[:200], evidence='rule', source_type='announcement', source_id=ann.id)
                            self.db.add(risk_event)
                            self.db.flush()
                            EvidenceRuleService(self.db).create_from_risk_event(risk_event)
                        elif ann.is_business_update or ann.need_manual_review:
                            EvidenceRuleService(self.db).create_from_source_item('announcement', ann)
                        result['inserted'] += 1
                        if settings.ai_auto_analyze_important_items and ann.importance_score >= settings.ai_auto_analyze_importance_threshold:
                            LogicImpactService(self.db).analyze_announcement_logic(ann.id)
                            BusinessLineEvidenceService(self.db).create_evidence_from_announcement(ann.id)
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
