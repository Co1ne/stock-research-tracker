from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.models import Announcement, BusinessLine, BusinessLineEvidence, FinancialSnapshot, InvestmentHypothesis, NewsItem, RiskEvent


DEFAULT_FINANCIAL_LINE = '财务质量'
DEFAULT_GOVERNANCE_LINE = '公司治理'
DEFAULT_MAIN_LINE = '主营业务'


class EvidenceRuleService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_default_business_line(self, company_id: int, name: str, keywords: list[str] | None = None) -> BusinessLine:
        line = self.db.query(BusinessLine).filter(BusinessLine.company_id == company_id, BusinessLine.name == name).first()
        if line:
            return line
        line = BusinessLine(
            company_id=company_id,
            name=name,
            role='analysis_dimension',
            description=f'{name}默认分析维度，用于承接未能归因到具体业务线的规则证据。',
            keywords=keywords or [name],
            key_metrics='',
            confidence='medium',
            generated_by='rule',
        )
        self.db.add(line)
        self.db.flush()
        return line

    def create_from_risk_event(self, risk: RiskEvent) -> int:
        if not risk.company_id or not risk.source_id:
            return 0
        source = self._source_record(risk.source_type, risk.source_id)
        source_title = self._source_title(source, risk)
        text = f'{risk.title} {risk.description or ""} {source_title}'
        business_line = self._match_business_line(risk.company_id, text) or self._fallback_line(risk)
        hypothesis = self._match_hypothesis(risk.company_id, text, business_line.id if business_line else None)
        existing = self.db.query(BusinessLineEvidence).filter(
            and_(
                BusinessLineEvidence.company_id == risk.company_id,
                BusinessLineEvidence.source_type == risk.source_type,
                BusinessLineEvidence.source_id == risk.source_id,
                BusinessLineEvidence.business_line_id == (business_line.id if business_line else None),
                BusinessLineEvidence.title == risk.title,
            )
        ).first()
        if existing:
            return 0
        source_existing = self.db.query(BusinessLineEvidence).filter(
            BusinessLineEvidence.company_id == risk.company_id,
            BusinessLineEvidence.source_type == risk.source_type,
            BusinessLineEvidence.source_id == risk.source_id,
            BusinessLineEvidence.business_line_id == (business_line.id if business_line else None),
        ).first()
        if source_existing:
            return 0
        self.db.add(BusinessLineEvidence(
            company_id=risk.company_id,
            business_line_id=business_line.id if business_line else None,
            hypothesis_id=hypothesis.id if hypothesis else None,
            risk_event_id=risk.id,
            source_type=risk.source_type,
            source_id=risk.source_id,
            source_title=source_title,
            source_url=getattr(source, 'url', None),
            source_date=self._source_date(source),
            evidence_type='risk',
            direction='negative',
            logic_impact='weaken',
            severity=risk.level or 'medium',
            title=risk.title,
            summary=self._risk_summary(risk),
            reason=self._risk_reason(risk),
            confidence='rule',
            review_status='pending',
            need_manual_review=True,
        ))
        self._touch_hypothesis(hypothesis, risk.title) if hypothesis else None
        self.db.flush()
        return 1

    def create_from_source_item(self, source_type: str, item: Announcement | NewsItem) -> int:
        if not item.company_id:
            return 0
        if not (item.is_risk_event or item.need_manual_review or item.is_business_update or item.logic_impact):
            return 0
        text = f'{item.title} {item.summary or ""} {item.raw_text or ""}'
        business_line = self._match_business_line(item.company_id, text)
        hypothesis = self._match_hypothesis(item.company_id, text, business_line.id if business_line else None)
        evidence_type = 'risk' if item.is_risk_event else (item.evidence_type or 'uncertain')
        impact = item.logic_impact or ('weaken' if item.is_risk_event else 'uncertain')
        direction = {'strengthen': 'positive', 'weaken': 'negative', 'neutral': 'neutral'}.get(impact, 'uncertain')
        existing = self.db.query(BusinessLineEvidence).filter(
            BusinessLineEvidence.company_id == item.company_id,
            BusinessLineEvidence.source_type == source_type,
            BusinessLineEvidence.source_id == item.id,
            BusinessLineEvidence.business_line_id == (business_line.id if business_line else None),
            BusinessLineEvidence.title == item.title,
        ).first()
        if existing:
            return 0
        self.db.add(BusinessLineEvidence(
            company_id=item.company_id,
            business_line_id=business_line.id if business_line else None,
            hypothesis_id=hypothesis.id if hypothesis else None,
            source_type=source_type,
            source_id=item.id,
            source_title=item.title,
            source_url=item.url,
            source_date=item.publish_time,
            evidence_type=evidence_type,
            direction=direction,
            logic_impact=impact,
            severity='medium' if item.is_risk_event or item.need_manual_review else 'low',
            title=item.title,
            summary=item.summary or '',
            reason=item.ai_reason or ('规则识别到风险或需复核信息，先沉淀为待确认证据。' if item.is_risk_event or item.need_manual_review else '规则识别到业务线相关信息，需人工复核其影响。'),
            confidence=item.ai_confidence or 'rule',
            review_status='pending' if item.need_manual_review else 'confirmed',
            need_manual_review=item.need_manual_review,
        ))
        self._touch_hypothesis(hypothesis, item.title) if hypothesis else None
        self.db.flush()
        return 1

    def _source_record(self, source_type: str, source_id: int):
        model = {'announcement': Announcement, 'news': NewsItem, 'financial': FinancialSnapshot}.get(source_type)
        return self.db.get(model, source_id) if model else None

    def _source_title(self, source, risk: RiskEvent) -> str:
        if hasattr(source, 'title'):
            return source.title
        if hasattr(source, 'report_period'):
            return f'{source.report_period} 财务快照'
        return risk.title

    def _source_date(self, source):
        if hasattr(source, 'publish_time'):
            return source.publish_time
        return getattr(source, 'created_at', None)

    def _match_business_line(self, company_id: int, text: str) -> BusinessLine | None:
        lines = self.db.query(BusinessLine).filter(BusinessLine.company_id == company_id).all()
        for line in lines:
            if any(keyword and keyword in text for keyword in (line.keywords or [])):
                return line
        return None

    def _fallback_line(self, risk: RiskEvent) -> BusinessLine:
        text = f'{risk.title} {risk.description or ""}'
        if risk.source_type == 'financial' or any(word in text for word in ['现金流', '净利润', '毛利率', '应收', '存货', '财务']):
            return self.ensure_default_business_line(risk.company_id, DEFAULT_FINANCIAL_LINE, ['现金流', '净利润', '毛利率', '应收账款', '存货', '财务'])
        if any(word in text for word in ['减持', '处罚', '诉讼', '问询函', '担保']):
            return self.ensure_default_business_line(risk.company_id, DEFAULT_GOVERNANCE_LINE, ['减持', '处罚', '诉讼', '问询函', '担保'])
        return self.ensure_default_business_line(risk.company_id, DEFAULT_MAIN_LINE, ['主营业务', '业务', '收入', '订单', '客户'])

    def _match_hypothesis(self, company_id: int, text: str, business_line_id: int | None) -> InvestmentHypothesis | None:
        hypotheses = self.db.query(InvestmentHypothesis).filter(InvestmentHypothesis.company_id == company_id).all()
        for item in hypotheses:
            if business_line_id and business_line_id in (item.related_business_line_ids or []):
                return item
            if item.title and item.title in text:
                return item
        return hypotheses[0] if len(hypotheses) == 1 else None

    def _touch_hypothesis(self, hypothesis: InvestmentHypothesis, evidence_title: str):
        hypothesis.latest_evidence_summary = evidence_title
        hypothesis.status = 'at_risk'
        hypothesis.updated_at = datetime.utcnow()

    def _risk_summary(self, risk: RiskEvent) -> str:
        if risk.description:
            return risk.description
        return '规则识别到风险信号，需要人工复核其对经营质量和投资逻辑的影响。'

    def _risk_reason(self, risk: RiskEvent) -> str:
        if risk.source_type == 'financial' and '现金流' in risk.title:
            return '经营现金流与净利润背离可能意味着利润质量、回款能力或营运资金压力存在不确定性。'
        if '减持' in risk.title:
            return '减持相关信息可能影响股东行为预期，需要结合规模、主体和公司基本面复核。'
        if '亏损' in risk.title or '净利润' in risk.title:
            return '利润下滑或亏损会削弱盈利质量，需要结合收入、毛利率和现金流继续观察。'
        return '该事项命中风险规则，暂按负面/风险证据处理，等待人工确认。'
