from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Announcement, BusinessLine, BusinessLineEvidence, Company, FinancialSnapshot, InvestmentHypothesis, JobRun, NewsItem, Report, RiskEvent
from app.schemas.business_line import BusinessLineCreate, BusinessLineOut
from app.schemas.company import CompanyCreate, CompanyOut
from app.services.announcement_fetch_service import AnnouncementFetchService
from app.services.business_line_evidence_service import BusinessLineEvidenceService
from app.services.business_line_matcher import match_business_lines
from app.services.classification_service import classify_text
from app.services.company_initialization_service import CompanyInitializationService
from app.services.evidence_rule_service import EvidenceRuleService
from app.services.financial_fetch_service import FinancialFetchService
from app.services.job_run_service import JobRunService
from app.services.logic_impact_service import LogicImpactService
from app.services.news_fetch_service import NewsFetchService
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


@router.post('/companies/initialize')
def initialize_company(payload: dict, db: Session = Depends(get_db)):
    code = str(payload.get('code') or '').strip()
    if not code:
        raise HTTPException(400, 'code is required')
    return CompanyInitializationService(db).initialize(code, payload.get('market'))


@router.get('/companies/initialize/{task_id}')
def get_initialize_status(task_id: int, db: Session = Depends(get_db)):
    status = CompanyInitializationService(db).get_status(task_id)
    if not status:
        raise HTTPException(404, 'initialize task not found')
    return status


@router.post('/companies/initialize/{task_id}/confirm')
def confirm_initialize(task_id: int, payload: dict, db: Session = Depends(get_db)):
    result = CompanyInitializationService(db).confirm(task_id, payload)
    if not result:
        raise HTTPException(404, 'initialize task not found')
    return result


@router.get('/companies', response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).order_by(Company.id.desc()).all()


@router.get('/dashboard/summary')
def dashboard_summary(db: Session = Depends(get_db)):
    _backfill_missing_risk_evidence(db)
    today = datetime.utcnow().date()
    today_start = datetime(today.year, today.month, today.day)
    latest_runs = db.query(JobRun).order_by(JobRun.started_at.desc()).limit(5).all()
    failed = latest_runs[0].result_summary.get('failed_companies', []) if latest_runs and latest_runs[0].result_summary else []
    latest_evidence = db.query(BusinessLineEvidence).order_by(BusinessLineEvidence.created_at.desc()).limit(8).all()
    pending_evidence = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.review_status == 'pending').order_by(BusinessLineEvidence.created_at.desc()).limit(8).all()
    risk_rows = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.evidence_type == 'risk', BusinessLineEvidence.created_at >= today_start).order_by(BusinessLineEvidence.created_at.desc()).limit(8).all()
    return {
        'today_announcements': db.query(Announcement).filter(Announcement.created_at >= today_start).count(),
        'today_news': db.query(NewsItem).filter(NewsItem.created_at >= today_start).count(),
        'today_risks': db.query(RiskEvent).filter(RiskEvent.created_at >= today_start).count(),
        'today_evidence': db.query(BusinessLineEvidence).filter(BusinessLineEvidence.created_at >= today_start).count(),
        'latest_runs': [_job_run_out(i) for i in latest_runs],
        'failed_company_count': len(failed),
        'pending_ai_count': db.query(Announcement).filter(Announcement.logic_impact.is_(None), Announcement.importance_score >= 4).count() + db.query(NewsItem).filter(NewsItem.logic_impact.is_(None), NewsItem.importance_score >= 4).count(),
        'manual_review_count': db.query(BusinessLineEvidence).filter(BusinessLineEvidence.review_status == 'pending').count(),
        'today_focus': [_dashboard_focus_item(item, db) for item in risk_rows] or [_dashboard_focus_item(item, db) for item in latest_evidence[:3]],
        'pending_reviews': [_evidence_out(item, db) for item in pending_evidence],
        'latest_evidence': [_evidence_out(item, db) for item in latest_evidence],
        'risk_companies': _company_bucket(risk_rows, db),
        'strengthening_companies': _logic_company_bucket('strengthen', db),
        'weakening_companies': _logic_company_bucket('weaken', db),
    }


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
        risk_event = RiskEvent(company_id=company_id, event_type='rule_hit', level=level, title=title, description=raw_text[:200], evidence='rule', source_type='announcement', source_id=ann.id)
        db.add(risk_event)
        db.flush()
        from app.services.evidence_rule_service import EvidenceRuleService
        EvidenceRuleService(db).create_from_risk_event(risk_event)
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
        risk_event = RiskEvent(company_id=company_id, event_type='rule_hit', level=level, title=title, description=raw_text[:200], evidence='rule', source_type='news', source_id=item.id)
        db.add(risk_event)
        db.flush()
        from app.services.evidence_rule_service import EvidenceRuleService
        EvidenceRuleService(db).create_from_risk_event(risk_event)
    db.commit()
    return {'id': item.id}


@router.get('/feed')
def list_feed(company_id: int | None = None, source_type: Annotated[str | None, Query(pattern='^(announcement|news)$')] = None, category: str | None = None, min_importance: int | None = None, is_risk: bool | None = None, need_manual_review: bool | None = None, logic_impact: str | None = None, start_date: str | None = None, end_date: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50, db: Session = Depends(get_db)):
    rows = []
    if source_type in (None, 'announcement'):
        query = db.query(Announcement)
        if company_id is not None:
            query = query.filter(Announcement.company_id == company_id)
        query = _apply_feed_filters(query, Announcement, category, min_importance, is_risk, need_manual_review, logic_impact, start_date, end_date)
        for item in query.order_by(Announcement.publish_time.desc()).limit(limit).all():
            rows.append(_feed_item('announcement', item, db))
    if source_type in (None, 'news'):
        query = db.query(NewsItem)
        if company_id is not None:
            query = query.filter(NewsItem.company_id == company_id)
        query = _apply_feed_filters(query, NewsItem, category, min_importance, is_risk, need_manual_review, logic_impact, start_date, end_date)
        for item in query.order_by(NewsItem.publish_time.desc()).limit(limit).all():
            rows.append(_feed_item('news', item, db))

    rows.sort(key=lambda item: item['publish_time'] or item['created_at'], reverse=True)
    return rows[:limit]


@router.get('/announcements')
def list_announcements(company_id: int | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50, db: Session = Depends(get_db)):
    query = db.query(Announcement)
    if company_id is not None:
        query = query.filter(Announcement.company_id == company_id)
    return [_announcement_out(item, db) for item in query.order_by(Announcement.publish_time.desc()).limit(limit).all()]


@router.get('/news')
def list_news(company_id: int | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50, db: Session = Depends(get_db)):
    query = db.query(NewsItem)
    if company_id is not None:
        query = query.filter(NewsItem.company_id == company_id)
    return [_news_out(item, db) for item in query.order_by(NewsItem.publish_time.desc()).limit(limit).all()]


@router.post('/fetch/announcements')
def fetch_announcements(company_id: int | None = None, days: int | None = None, limit: int | None = None, db: Session = Depends(get_db)):
    return AnnouncementFetchService(db).fetch(company_id, days, limit)


@router.post('/fetch/news')
def fetch_news(company_id: int | None = None, days: int | None = None, limit: int | None = None, db: Session = Depends(get_db)):
    return NewsFetchService(db).fetch(company_id, days, limit)


@router.post('/fetch/financials')
def fetch_financials(company_id: int | None = None, db: Session = Depends(get_db)):
    return FinancialFetchService(db).fetch(company_id)


@router.get('/fetch/status')
def fetch_status(db: Session = Depends(get_db)):
    runs = db.query(JobRun).order_by(JobRun.started_at.desc()).limit(10).all()
    return {'recent_runs': [_job_run_out(i) for i in runs]}


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
    _backfill_missing_risk_evidence(db, id)
    items = BusinessLineEvidenceService(db).get_company_evidence(id, business_line_id, direction, evidence_type, logic_impact, days)
    return [_evidence_out(i, db) for i in items]


@router.get('/companies/{id}/hypotheses')
def company_hypotheses(id: int, db: Session = Depends(get_db)):
    company = db.get(Company, id)
    if not company:
        raise HTTPException(404, 'company not found')
    _ensure_company_hypotheses(company, db)
    items = db.query(InvestmentHypothesis).filter(InvestmentHypothesis.company_id == id).order_by(InvestmentHypothesis.id.asc()).all()
    return [_hypothesis_out(item, db) for item in items]


@router.get('/business-lines/{id}/evidence')
def business_line_evidence(id: int, db: Session = Depends(get_db)):
    items = BusinessLineEvidenceService(db).get_business_line_evidence(id)
    return [_evidence_out(i, db) for i in items]


@router.get('/risks')
def list_risks(company_id: int | None = None, resolved: bool | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50, db: Session = Depends(get_db)):
    query = db.query(RiskEvent)
    if company_id is not None:
        query = query.filter(RiskEvent.company_id == company_id)
    if resolved is not None:
        query = query.filter(RiskEvent.is_resolved == resolved)
    items = query.order_by(RiskEvent.created_at.desc()).limit(limit).all()
    return [{'id': i.id, 'company_id': i.company_id, 'event_type': i.event_type, 'level': i.level, 'title': i.title, 'description': i.description, 'evidence': i.evidence, 'source_type': i.source_type, 'source_id': i.source_id, 'is_resolved': i.is_resolved, 'created_at': i.created_at} for i in items]


@router.get('/companies/{id}/logic-summary')
def logic_summary(id: int, days: int = 30, db: Session = Depends(get_db)):
    _backfill_missing_risk_evidence(db, id)
    company = db.get(Company, id)
    if not company:
        raise HTTPException(404, 'company not found')
    _ensure_company_hypotheses(company, db)
    svc = BusinessLineEvidenceService(db)
    ev = svc.get_company_evidence(id, days=days)
    counts = {k: len([x for x in ev if x.direction == k]) for k in ['positive', 'negative', 'neutral', 'uncertain']}
    risk_count = len([x for x in ev if x.evidence_type == 'risk']) or db.query(RiskEvent).filter(RiskEvent.company_id == id, RiskEvent.created_at >= datetime.utcnow() - timedelta(days=days)).count()
    pending_count = len([x for x in ev if x.review_status == 'pending' or x.need_manual_review])
    status = 'uncertain'
    if risk_count >= 3:
        status = 'risk_rising'
    elif counts['negative'] >= 2 or risk_count >= 1:
        status = 'weakening'
    elif counts['positive'] >= 2 and counts['negative'] == 0:
        status = 'strengthening'
    elif ev:
        status = 'stable'

    lines = db.query(BusinessLine).filter(BusinessLine.company_id == id).all()
    line_stats = []
    for line in lines:
        line_evidence = [x for x in ev if x.business_line_id == line.id]
        line_announcements = len([item for item in db.query(Announcement).filter(Announcement.company_id == id).all() if line.name in (item.related_business_lines or [])])
        line_news = len([item for item in db.query(NewsItem).filter(NewsItem.company_id == id).all() if line.name in (item.related_business_lines or [])])
        latest = line_evidence[:3]
        line_stats.append({
            'business_line_id': line.id,
            'name': line.name,
            'description': line.description,
            'announcement_count': line_announcements,
            'news_count': line_news,
            'positive_count': len([x for x in line_evidence if x.direction == 'positive']),
            'negative_count': len([x for x in line_evidence if x.direction == 'negative']),
            'risk_count': len([x for x in line_evidence if x.evidence_type == 'risk']),
            'uncertain_count': len([x for x in line_evidence if x.direction == 'uncertain']),
            'pending_review_count': len([x for x in line_evidence if x.review_status == 'pending' or x.need_manual_review]),
            'latest_evidence': [_evidence_out(x, db) for x in latest],
            'updated_at': latest[0].created_at if latest else line.updated_at,
        })
    review_questions = _review_questions(company, ev, risk_count)
    system_summary = _system_summary(status, risk_count, pending_count, counts)
    return {
        'company_id': id,
        'positive_count': counts['positive'],
        'negative_count': counts['negative'],
        'neutral_count': counts['neutral'],
        'uncertain_count': counts['uncertain'],
        'risk_count': risk_count,
        'pending_review_count': pending_count,
        'business_lines': line_stats,
        'overall_status': status,
        'system_summary': system_summary,
        'review_questions': review_questions,
        'recent_changes': [_evidence_out(x, db) for x in ev[:5]],
    }


@router.get('/companies/{id}/financials')
def company_financials(id: int, db: Session = Depends(get_db)):
    items = db.query(FinancialSnapshot).filter(FinancialSnapshot.company_id == id).order_by(FinancialSnapshot.report_period.desc()).all()
    return [_financial_out(i) for i in items]


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
def list_reports(limit: Annotated[int, Query(ge=1, le=200)] = 50, db: Session = Depends(get_db)):
    items = db.query(Report).order_by(Report.created_at.desc()).limit(limit).all()
    return [{'id': i.id, 'company_id': i.company_id, 'report_type': i.report_type, 'title': i.title, 'period': i.period, 'conclusion': i.conclusion, 'risk_level': i.risk_level, 'created_at': i.created_at} for i in items]


@router.get('/reports/{id}')
def get_report(id: int, db: Session = Depends(get_db)):
    item = db.get(Report, id)
    if not item:
        raise HTTPException(404, 'report not found')
    return {'id': item.id, 'company_id': item.company_id, 'report_type': item.report_type, 'title': item.title, 'period': item.period, 'markdown_content': item.markdown_content, 'conclusion': item.conclusion, 'risk_level': item.risk_level, 'created_at': item.created_at}


@router.get('/jobs/runs')
def list_job_runs(limit: Annotated[int, Query(ge=1, le=200)] = 50, db: Session = Depends(get_db)):
    return [_job_run_out(i) for i in db.query(JobRun).order_by(JobRun.started_at.desc()).limit(limit).all()]


@router.post('/jobs/fetch-announcements')
def job_fetch_announcements(company_id: int | None = None, days: int | None = None, limit: int | None = None, db: Session = Depends(get_db)):
    return fetch_announcements(company_id, days, limit, db)


@router.post('/jobs/fetch-news')
def job_fetch_news(company_id: int | None = None, days: int | None = None, limit: int | None = None, db: Session = Depends(get_db)):
    return fetch_news(company_id, days, limit, db)


@router.post('/jobs/fetch-financials')
def job_fetch_financials(company_id: int | None = None, db: Session = Depends(get_db)):
    return fetch_financials(company_id, db)


@router.post('/jobs/generate-daily-report')
def job_generate_daily_report(db: Session = Depends(get_db)):
    run = JobRunService(db).start('generate_daily_report')
    try:
        result = make_daily_report(db)
        JobRunService(db).success(run, result)
        return result
    except Exception as exc:
        JobRunService(db).failed(run, str(exc))
        raise


@router.post('/jobs/generate-weekly-report')
def job_generate_weekly_report(db: Session = Depends(get_db)):
    return job_generate_daily_report(db)


def _apply_feed_filters(query, model, category, min_importance, is_risk, need_manual_review, logic_impact, start_date, end_date):
    if category:
        query = query.filter(model.category == category)
    if min_importance is not None:
        query = query.filter(model.importance_score >= min_importance)
    if is_risk is not None:
        query = query.filter(model.is_risk_event == is_risk)
    if need_manual_review is not None:
        query = query.filter(model.need_manual_review == need_manual_review)
    if logic_impact:
        query = query.filter(model.logic_impact == logic_impact)
    if start_date:
        query = query.filter(model.publish_time >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.filter(model.publish_time <= datetime.fromisoformat(end_date))
    return query


def _feed_item(source_type: str, item: Announcement | NewsItem, db: Session):
    company = db.get(Company, item.company_id) if item.company_id else None
    evidence = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.source_type == source_type, BusinessLineEvidence.source_id == item.id).all()
    line_names = []
    for ev in evidence:
        line = db.get(BusinessLine, ev.business_line_id) if ev.business_line_id else None
        if line and line.name not in line_names:
            line_names.append(line.name)
    impact = item.logic_impact or ('weaken' if item.is_risk_event else 'uncertain')
    analysis_status = 'pending_review' if item.need_manual_review else ('processed' if item.logic_impact or evidence else 'unprocessed')
    return {
        'id': item.id,
        'source_type': source_type,
        'company_id': item.company_id,
        'company_name': company.name if company else None,
        'stock_code': company.code if company else None,
        'title': item.title,
        'summary': item.summary,
        'source': item.source,
        'url': item.url,
        'category': item.category,
        'importance_score': item.importance_score,
        'is_risk_event': item.is_risk_event,
        'is_business_update': item.is_business_update,
        'related_business_lines': item.related_business_lines or [],
        'need_manual_review': item.need_manual_review,
        'ai_analyzed': bool(item.logic_impact),
        'logic_impact': item.logic_impact,
        'analysis_status': analysis_status,
        'impact_direction': impact,
        'generated_evidence_count': len(evidence),
        'need_review': item.need_manual_review or any(ev.review_status == 'pending' for ev in evidence),
        'related_business_line_names': line_names or (item.related_business_lines or []),
        'publish_time': item.publish_time,
        'fetched_at': item.created_at,
        'created_at': item.created_at,
    }


def _announcement_out(item: Announcement, db: Session):
    return _feed_item('announcement', item, db)


def _news_out(item: NewsItem, db: Session):
    return _feed_item('news', item, db)


def _financial_out(item: FinancialSnapshot):
    return {'id': item.id, 'company_id': item.company_id, 'stock_code': item.stock_code, 'report_period': item.report_period, 'revenue': item.revenue, 'net_profit': item.net_profit, 'net_profit_deducted': item.net_profit_deducted, 'gross_margin': item.gross_margin, 'net_margin': item.net_margin, 'operating_cash_flow': item.operating_cash_flow, 'accounts_receivable': item.accounts_receivable, 'inventory': item.inventory, 'debt_asset_ratio': item.debt_asset_ratio, 'roe': item.roe, 'source': item.source, 'created_at': item.created_at, 'updated_at': item.updated_at}


def _job_run_out(item: JobRun):
    return {'id': item.id, 'job_name': item.job_name, 'status': item.status, 'started_at': item.started_at, 'finished_at': item.finished_at, 'result_summary': item.result_summary, 'error_message': item.error_message}


def _evidence_out(item: BusinessLineEvidence, db: Session):
    company = db.get(Company, item.company_id)
    line = db.get(BusinessLine, item.business_line_id) if item.business_line_id else None
    hypothesis = db.get(InvestmentHypothesis, item.hypothesis_id) if item.hypothesis_id else None
    return {
        'id': item.id,
        'stock_code': company.code if company else None,
        'company_id': item.company_id,
        'company_name': company.name if company else None,
        'source_type': item.source_type,
        'source_id': item.source_id,
        'source_title': item.source_title or item.title,
        'source_url': item.source_url,
        'source_date': item.source_date,
        'business_line_id': item.business_line_id,
        'business_line_name': line.name if line else None,
        'hypothesis_id': item.hypothesis_id,
        'hypothesis_title': hypothesis.title if hypothesis else None,
        'evidence_type': item.evidence_type,
        'direction': item.direction,
        'impact_direction': item.logic_impact,
        'logic_impact': item.logic_impact,
        'severity': item.severity,
        'title': item.title,
        'summary': item.summary,
        'reason': item.reason,
        'confidence': item.confidence,
        'review_status': item.review_status,
        'need_manual_review': item.need_manual_review,
        'ai_summary': item.ai_summary,
        'ai_impact_judgment': item.ai_impact_judgment,
        'ai_reason': item.ai_reason,
        'ai_confidence': item.ai_confidence,
        'ai_generated_at': item.ai_generated_at,
        'manual_override': item.manual_override,
        'manual_note': item.manual_note,
        'created_at': item.created_at,
        'updated_at': item.updated_at,
    }


def _hypothesis_out(item: InvestmentHypothesis, db: Session):
    ev = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.hypothesis_id == item.id).all()
    positive = len([x for x in ev if x.direction == 'positive'])
    negative = len([x for x in ev if x.direction == 'negative'])
    risk = len([x for x in ev if x.evidence_type == 'risk'])
    uncertain = len([x for x in ev if x.direction == 'uncertain'])
    status = item.status
    if risk >= 2:
        status = 'at_risk'
    elif negative >= 2:
        status = 'weakened'
    elif positive >= 2 and negative == 0 and risk == 0:
        status = 'strengthened'
    elif ev:
        status = 'stable'
    return {
        'id': item.id,
        'stock_code': db.get(Company, item.company_id).code if db.get(Company, item.company_id) else None,
        'company_id': item.company_id,
        'title': item.title,
        'description': item.description,
        'related_business_line_ids': item.related_business_line_ids or [],
        'falsification_conditions': item.falsification_conditions or [],
        'status': status,
        'positive_evidence_count': positive,
        'negative_evidence_count': negative,
        'risk_evidence_count': risk,
        'uncertain_evidence_count': uncertain,
        'latest_evidence_summary': item.latest_evidence_summary or (ev[0].title if ev else None),
        'review_status': item.review_status,
        'created_at': item.created_at,
        'updated_at': item.updated_at,
    }


def _ensure_company_hypotheses(company: Company, db: Session):
    if db.query(InvestmentHypothesis).filter(InvestmentHypothesis.company_id == company.id).count():
        return
    title = (company.thesis or '').strip().split('\n')[0][:80] or f'{company.name} 核心经营逻辑待验证'
    falsification = [line.strip('- ').strip() for line in (company.disproof_conditions or '').split('\n') if line.strip()]
    if not falsification:
        falsification = ['长期缺少订单、收入、客户或项目落地证据', '财务质量持续转弱或风险事件持续增加']
    line_ids = [line.id for line in db.query(BusinessLine).filter(BusinessLine.company_id == company.id).limit(3).all()]
    db.add(InvestmentHypothesis(
        company_id=company.id,
        title=title,
        description=company.thesis or '由公司基础信息自动生成的待验证投资假设，需人工复核。',
        related_business_line_ids=line_ids,
        falsification_conditions=falsification,
        status='unverified',
        review_status='pending',
        generated_by='rule',
    ))
    db.commit()


def _review_questions(company: Company, evidence: list[BusinessLineEvidence], risk_count: int):
    pending = [x for x in evidence if x.review_status == 'pending' or x.need_manual_review]
    questions = []
    for item in pending[:5]:
        if item.evidence_type == 'risk':
            questions.append(f'{item.title} 是否持续，并是否接近证伪条件？')
        else:
            questions.append(f'{item.title} 对核心业务线影响是否明确？')
    if not questions and risk_count:
        questions.append('已有风险信号是否影响核心投资假设，需要人工复核。')
    if not questions:
        questions.append('暂无足够证据形成明确复核问题。')
    return questions


def _system_summary(status: str, risk_count: int, pending_count: int, counts: dict):
    if status == 'risk_rising':
        return f'存在 {risk_count} 条需跟踪风险信号，建议优先复核风险是否接近证伪条件。'
    if status == 'weakening':
        return f'负面或风险证据增加，当前有 {risk_count} 条风险证据、{pending_count} 条待复核事项。'
    if status == 'strengthening':
        return f'近期正面证据较多，暂未发现明显负面证据；仍需持续跟踪可持续性。'
    if status == 'stable':
        return f'暂无足够证据证明核心投资逻辑被削弱，目前有 {pending_count} 条待复核事项。'
    return '暂无足够证据形成判断，请先抓取公告、新闻和财务数据。'


def _dashboard_focus_item(item: BusinessLineEvidence, db: Session):
    company = db.get(Company, item.company_id)
    return {
        'company_id': item.company_id,
        'company_name': company.name if company else None,
        'stock_code': company.code if company else None,
        'title': item.title,
        'summary': item.summary,
        'severity': item.severity,
        'review_status': item.review_status,
        'created_at': item.created_at,
    }


def _company_bucket(items: list[BusinessLineEvidence], db: Session):
    bucket = {}
    for item in items:
        company = db.get(Company, item.company_id)
        if not company:
            continue
        bucket.setdefault(company.id, {'company_id': company.id, 'company_name': company.name, 'stock_code': company.code, 'count': 0})
        bucket[company.id]['count'] += 1
    return list(bucket.values())


def _logic_company_bucket(impact: str, db: Session):
    rows = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.logic_impact == impact).order_by(BusinessLineEvidence.created_at.desc()).limit(20).all()
    return _company_bucket(rows, db)


def _backfill_missing_risk_evidence(db: Session, company_id: int | None = None):
    query = db.query(RiskEvent)
    if company_id is not None:
        query = query.filter(RiskEvent.company_id == company_id)
    risks = query.order_by(RiskEvent.created_at.desc()).limit(200).all()
    created = 0
    service = EvidenceRuleService(db)
    for risk in risks:
        if not risk.source_id or not risk.company_id:
            continue
        exists = db.query(BusinessLineEvidence).filter(
            BusinessLineEvidence.risk_event_id == risk.id
        ).first()
        if exists:
            continue
        created += service.create_from_risk_event(risk)
    if created:
        db.commit()
