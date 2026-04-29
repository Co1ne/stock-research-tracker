from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Announcement, BusinessLine, BusinessLineEvidence, Company, NewsItem, Report, RiskEvent
from app.schemas.business_line import BusinessLineCreate, BusinessLineOut
from app.schemas.company import CompanyCreate, CompanyOut
from app.services.business_line_evidence_service import BusinessLineEvidenceService
from app.services.business_line_matcher import match_business_lines
from app.services.classification_service import classify_text
from app.services.logic_impact_service import LogicImpactService
from app.services.risk_rule_service import detect_risk

router = APIRouter(prefix='/api')

@router.get('/health')
def health(): return {'status': 'ok'}

@router.post('/companies', response_model=CompanyOut)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    item = Company(**payload.model_dump()); db.add(item); db.commit(); db.refresh(item); return item

@router.get('/companies', response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)): return db.query(Company).order_by(Company.id.desc()).all()

@router.post('/business-lines', response_model=BusinessLineOut)
def create_business_line(payload: BusinessLineCreate, db: Session = Depends(get_db)):
    if not db.get(Company, payload.company_id): raise HTTPException(404, 'company not found')
    item = BusinessLine(**payload.model_dump()); db.add(item); db.commit(); db.refresh(item); return item

@router.post('/mock/announcement')
def mock_announcement(company_id: int, title: str, raw_text: str, db: Session = Depends(get_db)):
    lines = db.query(BusinessLine).filter(BusinessLine.company_id == company_id).all(); matched = match_business_lines(title + raw_text, [{'name': l.name, 'keywords': l.keywords or []} for l in lines]); risk, level = detect_risk(title + raw_text)
    ann = Announcement(company_id=company_id, title=title, raw_text=raw_text, publish_time=datetime.utcnow(), source='mock', category=classify_text(title + raw_text), importance_score=5 if risk else 3, is_risk_event=risk, is_business_update=bool(matched), related_business_lines=matched, need_manual_review=risk)
    db.add(ann); db.flush()
    if risk: db.add(RiskEvent(company_id=company_id, event_type='rule_hit', level=level, title=title, description=raw_text[:200], evidence='rule', source_type='announcement', source_id=ann.id))
    db.commit(); return {'id': ann.id}

@router.post('/mock/news')
def mock_news(company_id: int, title: str, raw_text: str, db: Session = Depends(get_db)):
    item = NewsItem(title=title, raw_text=raw_text, publish_time=datetime.utcnow(), source='mock', company_id=company_id, importance_score=4)
    db.add(item); db.commit(); return {'id': item.id}

@router.post('/announcements/{id}/analyze-logic')
def analyze_announcement(id: int, db: Session = Depends(get_db)):
    item = LogicImpactService(db).analyze_announcement_logic(id)
    created = BusinessLineEvidenceService(db).create_evidence_from_announcement(id)
    return {'id': item.id, 'logic_impact': item.logic_impact, 'evidence_created': created}

@router.post('/news/{id}/analyze-logic')
def analyze_news(id: int, db: Session = Depends(get_db)):
    item = LogicImpactService(db).analyze_news_logic(id)
    created = BusinessLineEvidenceService(db).create_evidence_from_news(id)
    return {'id': item.id, 'logic_impact': item.logic_impact, 'evidence_created': created}

@router.post('/logic-analysis/run-pending')
def run_pending(limit: int = 20, db: Session = Depends(get_db)):
    return LogicImpactService(db).batch_analyze_pending_items(limit)

@router.get('/companies/{id}/evidence')
def company_evidence(id: int, business_line_id: int | None = None, direction: str | None = None, evidence_type: str | None = None, logic_impact: str | None = None, days: int = 30, db: Session = Depends(get_db)):
    items = BusinessLineEvidenceService(db).get_company_evidence(id, business_line_id, direction, evidence_type, logic_impact, days)
    return [{'id': i.id, 'title': i.title, 'business_line_id': i.business_line_id, 'direction': i.direction, 'evidence_type': i.evidence_type, 'logic_impact': i.logic_impact, 'confidence': i.confidence, 'reason': i.reason, 'created_at': i.created_at} for i in items]

@router.get('/business-lines/{id}/evidence')
def business_line_evidence(id: int, db: Session = Depends(get_db)):
    items = BusinessLineEvidenceService(db).get_business_line_evidence(id)
    return [{'id': i.id, 'title': i.title, 'direction': i.direction} for i in items]

@router.get('/companies/{id}/logic-summary')
def logic_summary(id: int, days: int = 30, db: Session = Depends(get_db)):
    svc = BusinessLineEvidenceService(db); ev = svc.get_company_evidence(id, days=days)
    counts = {k: len([x for x in ev if x.direction == k]) for k in ['positive', 'negative', 'neutral', 'uncertain']}
    risk_count = db.query(RiskEvent).filter(RiskEvent.company_id == id, RiskEvent.level == 'high', RiskEvent.created_at >= datetime.utcnow() - timedelta(days=days)).count()
    status = 'uncertain'
    if counts['negative'] >= 2 or risk_count >= 1: status = 'weakening'
    elif counts['positive'] >= 2 and counts['negative'] == 0: status = 'strengthening'
    elif counts['positive'] == 0 and counts['negative'] == 0: status = 'stable'
    lines = db.query(BusinessLine).filter(BusinessLine.company_id == id).all()
    line_stats = []
    for l in lines:
        le = [x for x in ev if x.business_line_id == l.id]
        line_stats.append({'business_line_id': l.id, 'name': l.name, 'positive_count': len([x for x in le if x.direction == 'positive']), 'negative_count': len([x for x in le if x.direction == 'negative']), 'latest_evidence': [x.title for x in le[:3]]})
    return {'company_id': id, 'positive_count': counts['positive'], 'negative_count': counts['negative'], 'neutral_count': counts['neutral'], 'uncertain_count': counts['uncertain'], 'risk_count': risk_count, 'business_lines': line_stats, 'overall_status': status}

@router.post('/reports/daily')
def make_daily_report(db: Session = Depends(get_db)):
    companies = db.query(Company).all(); sections=[]
    for c in companies:
        s=logic_summary(c.id,7,db)
        sections.append(f"## {c.name} 投资逻辑验证\n- 本周正面证据：{s['positive_count']} 条\n- 本周负面证据：{s['negative_count']} 条\n- 风险事件：{s['risk_count']} 条\n- 初步判断：{s['overall_status']}\n")
    md = '# 周报\n\n' + '\n'.join(sections)
    r = Report(report_type='weekly', title='系统周报', period=datetime.utcnow().strftime('%Y-W%W'), markdown_content=md, conclusion='仅供经营跟踪，不构成投资建议', risk_level='medium')
    db.add(r); db.commit(); return {'report_id': r.id}
