from datetime import datetime

from sqlalchemy.orm import Session

from app.ai.mock_provider import MockAIProvider
from app.ai.openai_provider import OpenAIProvider
from app.core.config import settings
from app.models.models import AITask, Announcement, BusinessLine, Company, NewsItem
from app.services.ai_service import AIService

PROMPT_VERSION = 'v2.logic.1'


class LogicImpactService:
    def __init__(self, db: Session):
        self.db = db
        provider = MockAIProvider() if settings.ai_provider != 'openai' else OpenAIProvider()
        self.ai_service = AIService(provider)

    def _build_payload(self, company: Company, lines: list[BusinessLine], item: Announcement | NewsItem, source_type: str) -> dict:
        return {
            'company': {'name': company.name, 'code': company.code, 'thesis': company.thesis or '', 'disproof_conditions': company.disproof_conditions or ''},
            'business_lines': [{'id': l.id, 'name': l.name, 'role': l.role, 'description': l.description, 'keywords': l.keywords or []} for l in lines],
            'item': {'source_type': source_type, 'title': item.title, 'summary': item.summary or '', 'raw_text': item.raw_text or '', 'category': item.category or '', 'importance_score': item.importance_score, 'is_risk_event': item.is_risk_event},
        }

    def _analyze(self, item, source_type: str):
        if item.logic_impact and item.prompt_version == PROMPT_VERSION and item.ai_confidence:
            return item
        company = self.db.get(Company, item.company_id)
        lines = self.db.query(BusinessLine).filter(BusinessLine.company_id == company.id).all() if company else []
        task = AITask(task_type='logic_impact', status='running', provider=settings.ai_provider, model=settings.ai_model_fast or 'mock', input_ref_type=source_type, input_ref_id=item.id, started_at=datetime.utcnow())
        self.db.add(task)
        self.db.flush()
        payload = self._build_payload(company, lines, item, source_type)
        try:
            result = self.ai_service.analyze_logic_impact(payload)
            task.status = 'success'
        except Exception as e:
            result = {'logic_impact': 'uncertain', 'evidence_type': 'other', 'confidence': 'low', 'reason': f'AI调用失败: {e}', 'need_manual_review': True, 'related_business_line_ids': []}
            task.status = 'failed'
            task.error_message = str(e)
        task.finished_at = datetime.utcnow()
        item.logic_impact = result['logic_impact']
        item.evidence_type = result['evidence_type']
        item.ai_confidence = result['confidence']
        item.ai_reason = result['reason']
        item.need_manual_review = bool(result.get('need_manual_review', False))
        item.ai_analyzed_at = datetime.utcnow()
        item.prompt_version = PROMPT_VERSION
        self.db.commit()
        self.db.refresh(item)
        return item

    def analyze_announcement_logic(self, announcement_id: int):
        return self._analyze(self.db.get(Announcement, announcement_id), 'announcement')

    def analyze_news_logic(self, news_id: int):
        return self._analyze(self.db.get(NewsItem, news_id), 'news')

    def batch_analyze_pending_items(self, limit: int = 20):
        anns = self.db.query(Announcement).filter(Announcement.logic_impact.is_(None)).limit(limit).all()
        news = self.db.query(NewsItem).filter(NewsItem.logic_impact.is_(None)).limit(limit).all()
        for a in anns:
            self._analyze(a, 'announcement')
        for n in news:
            self._analyze(n, 'news')
        return {'announcements': len(anns), 'news': len(news)}
