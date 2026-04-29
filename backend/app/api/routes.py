from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Announcement, BusinessLine, Company, NewsItem, Report, RiskEvent
from app.schemas.business_line import BusinessLineCreate, BusinessLineOut
from app.schemas.company import CompanyCreate, CompanyOut
from app.services.business_line_evidence_service import BusinessLineEvidenceService
from app.services.business_line_matcher import match_business_lines
from app.services.classification_service import classify_text
from app.services.logic_impact_service import LogicImpactService
from app.services.risk_rule_service import detect_risk

router = APIRouter(prefix='/api')


@router.get('/health')
def health():
    return {'status': 'ok'}


@router.post('/companies', response_model=CompanyOut)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    item = Company(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get('/companies', response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).order_by(Company.id.desc()).all()


@router.post('/business-lines', response_model=BusinessLineOut)
def create_business_line(payload: BusinessLineCreate, db: Session = Depends(get_db)):
    if not db.get(Company, payload.company_id):
        raise HTTPException(404, 'company not found')
    item = BusinessLine(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get('/companies/{id}/business-lines', response_model=list[BusinessLineOut])
def list_company_business_lines(id: int, db: Session = Depends(get_db)):
    if not db.get(Company, id):
        raise HTTPException(404, 'company not found')
    return db.query(BusinessLine).filter(BusinessLine.company_id == id).order_by(BusinessLine.id.desc()).all()


@router.post('/mock/announcement')
def mock_announcement(company_id: int, title: str, raw_text: str, db: Session = Depends(get_db)):
    if not db.get(Company, company_id):
        raise HTTPException(404, 'company not found')

    text = title + raw_text
    lines = db.query(BusinessLine).filter(BusinessLine.company_id == company_id).all()
    matched = match_business_lines(text, [{'name': line.name, 'keywords': line.keywords or []} for line in lines])
    risk, level = detect_risk(text)
    ann = Announcement(
        company_id=company_id,
        title=title,
        raw_text=raw_text,
        publish_time=datetime.utcnow(),
        source='mock',
        category=classify_text(text),
        importance_score=5 if risk else 3,
        is_risk_event=risk,
        is_business_update=bool(matched),
        related_business_lines=matched,
        need_manual_review=risk,
    )
    db.add(ann)
    db.flush()
    if risk:
        db.add(RiskEvent(company_id=company_id, event_type='rule_hit', level=level, title=title, description=raw_text[:200], evidence='rule', source_type='announcement', source_id=ann.id))
    db.commit()
    return {'id': ann.id}


@router.post('/mock/news')
def mock_news(company_id: int, title: str, raw_text: str, db: Session = Depends(get_db)):
    if not db.get(Company, company_id):
        raise HTTPException(404, 'company not found')

    text = title + raw_text
    lines = db.query(BusinessLine).filter(BusinessLine.company_id == company_id).all()
    matched = match_business_lines(text, [{'name': line.name, 'keywords': line.keywords or []} for line in lines])
    risk, level = detect_risk(text)
    item = NewsItem(
        title=title,
        raw_text=raw_text,
        publish_time=datetime.utcnow(),
        source='mock',
        company_id=company_id,
        category=classify_text(text),
        importance_score=5 if risk else 4,
        is_risk_event=risk,
        is_business_update=bool(matched),
        related_business_lines=matched,
        need_manual_review=risk,
    )
    db.add(item)
    db.flush()
    if risk:
        db.add(RiskEvent(company_id=company_id, event_type='rule_hit', level=level, title=title, description=raw_text[:200], evidence='rule', source_type='news', source_id=item.id))
    db.commit()
    return {'id': item.id}


@router.get('/feed')
def list_feed(company_id: int | None = None, source_type: str | None = Query(default=None, pattern='^(announcement|news)$'), limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    rows = []
    if source_type in (None, 'announcement'):
        query = db.query(Announcement)
        if company_id is not None:
            query = query.filter(Announcement.company_id == company_id)
        for item in query.order_by(Announcement.publish_time.desc()).limit(limit).all():
            rows.append(_feed_item('announcement', item))
    if source_type in (None, 'news'):
        query = db.query(NewsItem)
        if company_id is not None:
            query = query.filter(NewsItem.company_id == company_id)
        for item in query.order_by(NewsItem.publish_time.desc()).limit(limit).all():
            rows.append(_feed_item('news', item))

    rows.sort(key=lambda item: item['publish_time'] or item['created_at'], reverse=True)
    return rows[:limit]


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


@router.get('/risks')
def list_risks(company_id: int | None = None, resolved: bool | None = None, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    query = db.query(RiskEvent)
    if company_id is not None:
        query = query.filter(RiskEvent.company_id == company_id)
    if resolved is not None:
        query = query.filter(RiskEvent.is_resolved == resolved)
    items = query.order_by(RiskEvent.created_at.desc()).limit(limit).all()
    return [{'id': i.id, 'company_id': i.company_id, 'event_type': i.event_type, 'level': i.level, 'title': i.title, 'description': i.description, 'evidence': i.evidence, 'source_type': i.source_type, 'source_id': i.source_id, 'is_resolved': i.is_resolved, 'created_at': i.created_at} for i in items]


@router.get('/companies/{id}/logic-summary')
def logic_summary(id: int, days: int = 30, db: Session = Depends(get_db)):
    svc = BusinessLineEvidenceService(db)
    ev = svc.get_company_evidence(id, days=days)
    counts = {k: len([x for x in ev if x.direction == k]) for k in ['positive', 'negative', 'neutral', 'uncertain']}
    risk_count = db.query(RiskEvent).filter(RiskEvent.company_id == id, RiskEvent.level == 'high', RiskEvent.created_at >= datetime.utcnow() - timedelta(days=days)).count()
    status = 'uncertain'
    if counts['negative'] >= 2 or risk_count >= 1:
        status = 'weakening'
    elif counts['positive'] >= 2 and counts['negative'] == 0:
        status = 'strengthening'
    elif counts['positive'] == 0 and counts['negative'] == 0:
        status = 'stable'

    lines = db.query(BusinessLine).filter(BusinessLine.company_id == id).all()
    line_stats = []
    for line in lines:
        line_evidence = [x for x in ev if x.business_line_id == line.id]
        line_stats.append({'business_line_id': line.id, 'name': line.name, 'positive_count': len([x for x in line_evidence if x.direction == 'positive']), 'negative_count': len([x for x in line_evidence if x.direction == 'negative']), 'latest_evidence': [x.title for x in line_evidence[:3]]})
    return {'company_id': id, 'positive_count': counts['positive'], 'negative_count': counts['negative'], 'neutral_count': counts['neutral'], 'uncertain_count': counts['uncertain'], 'risk_count': risk_count, 'business_lines': line_stats, 'overall_status': status}


@router.post('/reports/daily')
def make_daily_report(db: Session = Depends(get_db)):
    companies = db.query(Company).order_by(Company.id.asc()).all()
    sections = []
    for company in companies:
        summary = logic_summary(company.id, 7, db)
        sections.append(f"## {company.name} 投资逻辑验证\n- 本周正面证据：{summary['positive_count']} 条\n- 本周负面证据：{summary['negative_count']} 条\n- 风险事件：{summary['risk_count']} 条\n- 初步判断：{summary['overall_status']}\n")
    md = '# 周报\n\n' + ('\n'.join(sections) if sections else '暂无自选公司。')
    report = Report(report_type='weekly', title='系统周报', period=datetime.utcnow().strftime('%Y-W%W'), markdown_content=md, conclusion='仅供经营跟踪，不构成投资建议', risk_level='medium')
    db.add(report)
    db.commit()
    db.refresh(report)
    return {'report_id': report.id}


@router.get('/reports')
def list_reports(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    items = db.query(Report).order_by(Report.created_at.desc()).limit(limit).all()
    return [{'id': i.id, 'company_id': i.company_id, 'report_type': i.report_type, 'title': i.title, 'period': i.period, 'conclusion': i.conclusion, 'risk_level': i.risk_level, 'created_at': i.created_at} for i in items]


@router.get('/reports/{id}')
def get_report(id: int, db: Session = Depends(get_db)):
    item = db.get(Report, id)
    if not item:
        raise HTTPException(404, 'report not found')
    return {'id': item.id, 'company_id': item.company_id, 'report_type': item.report_type, 'title': item.title, 'period': item.period, 'markdown_content': item.markdown_content, 'conclusion': item.conclusion, 'risk_level': item.risk_level, 'created_at': item.created_at}


def _feed_item(source_type: str, item: Announcement | NewsItem):
    return {
        'id': item.id,
        'source_type': source_type,
        'company_id': item.company_id,
        'title': item.title,
        'summary': item.summary,
        'category': item.category,
        'importance_score': item.importance_score,
        'is_risk_event': item.is_risk_event,
        'is_business_update': item.is_business_update,
        'logic_impact': item.logic_impact,
        'publish_time': item.publish_time,
        'created_at': item.created_at,
    }
