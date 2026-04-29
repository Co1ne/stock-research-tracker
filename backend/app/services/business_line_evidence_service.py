from datetime import datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.models import Announcement, BusinessLine, BusinessLineEvidence, NewsItem, RiskEvent


class BusinessLineEvidenceService:
    def __init__(self, db: Session):
        self.db = db

    def _direction(self, logic_impact: str) -> str:
        return {'strengthen': 'positive', 'weaken': 'negative', 'neutral': 'neutral'}.get(logic_impact, 'uncertain')

    def _should_create(self, item) -> bool:
        return item.importance_score >= 4 or item.is_risk_event or item.logic_impact in ['strengthen', 'weaken'] or item.need_manual_review or item.evidence_type in ['order', 'customer', 'product', 'financial', 'risk', 'policy']

    def _matched_lines(self, company_id: int, text: str):
        lines = self.db.query(BusinessLine).filter(BusinessLine.company_id == company_id).all()
        return [l for l in lines if any(k in text for k in (l.keywords or []))]

    def _create(self, source_type: str, source_id: int, company_id: int, title: str, summary: str, logic_impact: str, evidence_type: str, reason: str, confidence: str, need_manual_review: bool, text: str):
        lines = self._matched_lines(company_id, text)
        target_ids = [l.id for l in lines] or [None]
        source = self.db.get(Announcement, source_id) if source_type == 'announcement' else self.db.get(NewsItem, source_id)
        count = 0
        for bl_id in target_ids:
            exists = self.db.query(BusinessLineEvidence).filter(and_(BusinessLineEvidence.source_type == source_type, BusinessLineEvidence.source_id == source_id, BusinessLineEvidence.business_line_id.is_(bl_id))).first()
            if exists:
                continue
            direction = self._direction(logic_impact)
            self.db.add(BusinessLineEvidence(
                company_id=company_id,
                business_line_id=bl_id,
                source_type=source_type,
                source_id=source_id,
                source_title=title,
                source_url=getattr(source, 'url', None),
                source_date=getattr(source, 'publish_time', None),
                evidence_type=evidence_type or 'other',
                direction=direction,
                logic_impact=logic_impact or 'uncertain',
                severity='medium' if need_manual_review or direction == 'negative' else 'low',
                title=title,
                summary=summary,
                reason=reason,
                confidence=confidence or 'rule',
                review_status='pending' if need_manual_review else 'confirmed',
                need_manual_review=need_manual_review,
            ))
            count += 1
        self.db.commit()
        return count

    def create_evidence_from_announcement(self, announcement_id: int):
        a = self.db.get(Announcement, announcement_id)
        if not a or not self._should_create(a):
            return 0
        return self._create('announcement', a.id, a.company_id, a.title, a.summary or '', a.logic_impact or 'uncertain', a.evidence_type or 'other', a.ai_reason or '', a.ai_confidence or 'low', a.need_manual_review, f"{a.title} {a.summary or ''} {a.raw_text or ''}")

    def create_evidence_from_news(self, news_id: int):
        n = self.db.get(NewsItem, news_id)
        if not n or not self._should_create(n):
            return 0
        return self._create('news', n.id, n.company_id, n.title, n.summary or '', n.logic_impact or 'uncertain', n.evidence_type or 'other', n.ai_reason or '', n.ai_confidence or 'low', n.need_manual_review, f"{n.title} {n.summary or ''} {n.raw_text or ''}")

    def rebuild_company_evidence(self, company_id: int):
        self.db.query(BusinessLineEvidence).filter(BusinessLineEvidence.company_id == company_id).delete()
        self.db.commit()

    def get_company_evidence(self, company_id: int, business_line_id=None, direction=None, evidence_type=None, logic_impact=None, days=30):
        q = self.db.query(BusinessLineEvidence).filter(BusinessLineEvidence.company_id == company_id, BusinessLineEvidence.created_at >= datetime.utcnow() - timedelta(days=days))
        if business_line_id:
            q = q.filter(BusinessLineEvidence.business_line_id == business_line_id)
        if direction:
            q = q.filter(BusinessLineEvidence.direction == direction)
        if evidence_type:
            q = q.filter(BusinessLineEvidence.evidence_type == evidence_type)
        if logic_impact:
            q = q.filter(BusinessLineEvidence.logic_impact == logic_impact)
        return q.order_by(BusinessLineEvidence.created_at.desc()).all()

    def get_business_line_evidence(self, business_line_id: int):
        return self.db.query(BusinessLineEvidence).filter(BusinessLineEvidence.business_line_id == business_line_id).order_by(BusinessLineEvidence.created_at.desc()).all()
