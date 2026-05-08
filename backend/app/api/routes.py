from datetime import datetime, timedelta
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Announcement, BusinessLine, BusinessLineEvidence, Company, DisciplineCheck, FinancialSnapshot, IngestionRun, InvestmentHypothesis, JobRun, NewsItem, Report, ResearchNote, RiskEvent
from app.schemas.business_line import BusinessLineCreate, BusinessLineOut
from app.schemas.company import CompanyCreate, CompanyOut
from app.services.announcement_fetch_service import AnnouncementFetchService
from app.services.business_line_evidence_service import BusinessLineEvidenceService
from app.services.business_line_matcher import match_business_lines
from app.services.classification_service import classify_text
from app.services.company_initialization_service import CompanyInitializationService
from app.services.evidence_rule_service import EvidenceRuleService
from app.services.financial_fetch_service import FinancialFetchService
from app.services.ingestion_service import INGESTION_TYPES, IngestionService, _ingestion_run_out
from app.services.job_run_service import JobRunService
from app.services.logic_impact_service import LogicImpactService
from app.services.news_fetch_service import NewsFetchService
from app.services.risk_rule_service import detect_risk

router = APIRouter(prefix='/api')

REVIEW_STATUSES = {'pending', 'approved', 'rejected', 'edited'}
INGESTION_STATUSES = {'success', 'partial_success', 'failed', 'skipped'}
CURRENT_VIEW_VALUES = {'bullish', 'neutral', 'cautious', 'negative'}
TRACKING_PRIORITY_VALUES = {'high', 'medium', 'low'}
HYPOTHESIS_RELATIONS = {'supports', 'contradicts', 'neutral', 'watch', 'unrelated'}
IMPACT_DIRECTIONS = {'positive', 'negative', 'neutral', 'unknown'}
IMPACT_STRENGTHS = {'high', 'medium', 'low'}
AFFECTED_ASPECTS = {'revenue', 'profit', 'margin', 'cashflow', 'order', 'shareholder', 'valuation', 'industry', 'policy', 'risk', 'business_line', 'other'}
HYPOTHESIS_LINK_FIELDS = {'hypothesis_id', 'hypothesis_relation', 'impact_direction', 'impact_strength', 'affected_aspect', 'evidence_summary', 'relation_note'}
RESEARCH_NOTE_TYPES = {'daily_note', 'event_review', 'hypothesis_update', 'risk_review', 'financial_review', 'manual_note'}
RESEARCH_NOTE_DIRECTIONS = {'strengthen', 'weaken', 'watch', 'neutral', 'risk'}
RESEARCH_NOTE_STATUSES = {'draft', 'active', 'archived'}
DISCIPLINE_CHECK_STATUSES = {'draft', 'completed', 'archived'}
DISCIPLINE_RESULTS = {'passed', 'blocked'}
DISCIPLINE_CHECKLIST_KEYS = {
    'has_clear_thesis',
    'evidence_reviewed',
    'risk_reviewed',
    'position_within_limit',
    'invalidation_defined',
    'no_pending_key_evidence',
    'no_rejected_core_evidence',
}


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
    _normalize_financial_evidence_source_dates(db)
    today = datetime.utcnow().date()
    today_start = datetime(today.year, today.month, today.day)
    recent_start = datetime.utcnow() - timedelta(days=30)
    latest_runs = db.query(JobRun).order_by(JobRun.started_at.desc()).limit(5).all()
    failed = latest_runs[0].result_summary.get('failed_companies', []) if latest_runs and latest_runs[0].result_summary else []
    latest_evidence = db.query(BusinessLineEvidence).order_by(BusinessLineEvidence.created_at.desc()).limit(8).all()
    pending_evidence = _filter_by_source_date(db.query(BusinessLineEvidence).filter(BusinessLineEvidence.review_status == 'pending').order_by(BusinessLineEvidence.created_at.desc()).limit(100).all(), recent_start)[:8]
    recent_source_evidence = _filter_by_source_date(db.query(BusinessLineEvidence).order_by(BusinessLineEvidence.created_at.desc()).limit(100).all(), today_start)
    unnoted_reviewed_evidence = _reviewed_evidence_without_research_note(db, limit=8)
    risk_rows = [item for item in recent_source_evidence if item.evidence_type == 'risk'][:8]
    return {
        'today_announcements': db.query(Announcement).filter(Announcement.created_at >= today_start).count(),
        'today_news': db.query(NewsItem).filter(NewsItem.created_at >= today_start).count(),
        'today_risks': db.query(RiskEvent).filter(RiskEvent.created_at >= today_start).count(),
        'today_evidence': len(recent_source_evidence),
        'latest_runs': [_job_run_out(i) for i in latest_runs],
        'failed_company_count': len(failed),
        'pending_ai_count': db.query(Announcement).filter(Announcement.logic_impact.is_(None), Announcement.importance_score >= 4).count() + db.query(NewsItem).filter(NewsItem.logic_impact.is_(None), NewsItem.importance_score >= 4).count(),
        'manual_review_count': len(pending_evidence),
        'today_focus': [_dashboard_focus_item(item, db) for item in risk_rows] or [_dashboard_focus_item(item, db) for item in recent_source_evidence[:3]],
        'pending_reviews': [_evidence_out(item, db) for item in pending_evidence],
        'latest_evidence': [_evidence_out(item, db) for item in latest_evidence],
        'reviewed_evidence_without_note_count': len(_reviewed_evidence_without_research_note(db, limit=500)),
        'reviewed_evidence_without_note': [_evidence_out(item, db) for item in unnoted_reviewed_evidence],
        'risk_companies': _company_bucket(risk_rows, db),
        'strengthening_companies': _logic_company_bucket('strengthen', db, recent_start),
        'weakening_companies': _logic_company_bucket('weaken', db, recent_start),
    }


@router.get('/dashboard/risk-board')
def dashboard_risk_board(db: Session = Depends(get_db)):
    companies = db.query(Company).filter(Company.status != 'removed').order_by(Company.id.asc()).all()
    rows = []
    status_counts = {f'{status}_count': 0 for status in ['unknown', 'stable', 'watching', 'risk_rising', 'weakened']}
    for company in companies:
        hypothesis = _current_hypothesis(company.id, db)
        if not hypothesis:
            status_counts['unknown_count'] += 1
            continue
        _ensure_hypothesis_evidence_links(company, hypothesis, db)
        items = _company_hypothesis_items(company.id, hypothesis.id, db)
        status = _hypothesis_status(items)
        status_counts[f'{status}_count'] = status_counts.get(f'{status}_count', 0) + 1
        rows.append(_risk_board_company_out(company, hypothesis, items, status))
    review_counts = {
        f'{status}_count': db.query(BusinessLineEvidence).filter(BusinessLineEvidence.review_status == status).count()
        for status in ['pending', 'approved', 'rejected', 'edited']
    }
    return {
        'review': review_counts,
        'hypothesis_status': status_counts,
        'risk_companies': [item for item in rows if item['hypothesis_status'] == 'risk_rising'],
        'weakened_companies': [item for item in rows if item['hypothesis_status'] == 'weakened'],
        'watching_companies': [item for item in rows if item['hypothesis_status'] == 'watching'],
        'missing_evidence_companies': [item for item in rows if item['hypothesis_status'] == 'unknown' and item['tracking_priority'] == 'high'],
    }


@router.get('/dashboard/ingestion-health')
def dashboard_ingestion_health(db: Session = Depends(get_db)):
    recent = db.query(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(50).all()
    sources = []
    for source_name in sorted({item.source_name for item in recent}):
        rows = [item for item in recent if item.source_name == source_name]
        last = rows[0] if rows else None
        sources.append({
            'source_name': source_name,
            'success_count': len([item for item in rows if item.status == 'success']),
            'failed_count': len([item for item in rows if item.status == 'failed']),
            'partial_success_count': len([item for item in rows if item.status == 'partial_success']),
            'last_status': last.status if last else None,
            'last_error_message': last.error_message if last else None,
            'last_run_at': last.started_at if last else None,
        })
    last_run = recent[0] if recent else None
    return {
        'last_run_at': last_run.started_at if last_run else None,
        'recent_success_count': len([item for item in recent if item.status == 'success']),
        'recent_failed_count': len([item for item in recent if item.status == 'failed']),
        'recent_partial_success_count': len([item for item in recent if item.status == 'partial_success']),
        'sources': sources,
        'recent_errors': [_ingestion_run_out(item, db) for item in recent if item.status == 'failed'][:5],
    }
@router.get('/review/pending')
def review_pending(limit: Annotated[int, Query(ge=1, le=200)] = 50, days: Annotated[int, Query(ge=0, le=3650)] = 30, db: Session = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(days=days) if days else None
    items = db.query(BusinessLineEvidence).filter(
        BusinessLineEvidence.review_status == 'pending'
    ).order_by(BusinessLineEvidence.created_at.desc()).limit(500).all()
    if cutoff:
        items = _filter_by_source_date(items, cutoff)
    return [_review_item_out(item, db) for item in items[:limit]]


@router.post('/review/items/{id}/decision')
def review_decision(id: int, payload: dict, db: Session = Depends(get_db)):
    item = db.get(BusinessLineEvidence, id)
    if not item:
        raise HTTPException(404, 'review item not found')
    status = str(payload.get('status') or '').strip()
    if status not in REVIEW_STATUSES or status == 'pending':
        raise HTTPException(400, 'status must be approved, rejected, or edited')
    note = payload.get('note')
    edited_content = payload.get('edited_content')
    if status == 'edited' and not str(edited_content or '').strip():
        raise HTTPException(400, 'edited_content is required when status is edited')

    if not item.original_content:
        item.original_content = _review_original_content(item)
    item.review_status = status
    item.reviewed_at = datetime.utcnow()
    item.reviewer = str(payload.get('reviewer') or 'local_user')
    item.review_note = str(note) if note is not None else None
    item.manual_note = item.review_note
    item.need_manual_review = False
    if status == 'edited':
        item.edited_content = str(edited_content)
        item.manual_override = True
    if _has_hypothesis_link_payload(payload):
        data = _normalize_hypothesis_link_payload(payload)
        _apply_hypothesis_link(item, data, db)
    _sync_source_review_status(item, db)
    db.commit()
    db.refresh(item)
    return _review_item_out(item, db)


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
def list_feed(company_id: int | None = None, source_type: Annotated[str | None, Query(pattern='^(announcement|news)$')] = None, source_name: str | None = None, category: str | None = None, min_importance: int | None = None, is_risk: bool | None = None, need_manual_review: bool | None = None, review_status: str | None = None, has_ingestion_run: bool | None = None, logic_impact: str | None = None, start_date: str | None = None, end_date: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50, db: Session = Depends(get_db)):
    _validate_enum_filter('review_status', review_status, REVIEW_STATUSES)
    rows = []
    if source_type in (None, 'announcement'):
        query = db.query(Announcement)
        if company_id is not None:
            query = query.filter(Announcement.company_id == company_id)
        if source_name:
            query = query.filter(Announcement.source_name == source_name)
        if has_ingestion_run is True:
            query = query.filter(Announcement.ingestion_run_id.is_not(None))
        if has_ingestion_run is False:
            query = query.filter(Announcement.ingestion_run_id.is_(None))
        query = _apply_feed_filters(query, Announcement, category, min_importance, is_risk, need_manual_review, logic_impact, start_date, end_date)
        for item in query.order_by(Announcement.publish_time.desc()).limit(limit).all():
            rows.append(_feed_item('announcement', item, db))
    if source_type in (None, 'news'):
        query = db.query(NewsItem)
        if company_id is not None:
            query = query.filter(NewsItem.company_id == company_id)
        if source_name:
            query = query.filter(NewsItem.source_name == source_name)
        if has_ingestion_run is True:
            query = query.filter(NewsItem.ingestion_run_id.is_not(None))
        if has_ingestion_run is False:
            query = query.filter(NewsItem.ingestion_run_id.is_(None))
        query = _apply_feed_filters(query, NewsItem, category, min_importance, is_risk, need_manual_review, logic_impact, start_date, end_date)
        for item in query.order_by(NewsItem.publish_time.desc()).limit(limit).all():
            rows.append(_feed_item('news', item, db))

    if review_status:
        rows = [item for item in rows if item.get('review_status') == review_status]
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


@router.post('/companies/{id}/ingest')
def ingest_company(id: int, payload: dict | None = None, db: Session = Depends(get_db)):
    company = db.get(Company, id)
    if not company:
        raise HTTPException(404, 'company not found')
    body = payload or {}
    types = body.get('types')
    force = bool(body.get('force', False))
    try:
        result = IngestionService(db).ingest_company(id, types, force)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@router.get('/ingestion/runs')
def list_ingestion_runs(company_id: int | None = None, source_name: str | None = None, source_type: str | None = None, status: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50, db: Session = Depends(get_db)):
    if source_type and source_type not in INGESTION_TYPES:
        raise HTTPException(400, 'invalid source_type')
    if status and status not in INGESTION_STATUSES:
        raise HTTPException(400, 'invalid status')
    query = db.query(IngestionRun)
    if company_id is not None:
        query = query.filter(IngestionRun.company_id == company_id)
    if source_name:
        query = query.filter(IngestionRun.source_name == source_name)
    if source_type:
        query = query.filter(IngestionRun.source_type == source_type)
    if status:
        query = query.filter(IngestionRun.status == status)
    return [_ingestion_run_out(item, db) for item in query.order_by(IngestionRun.started_at.desc()).limit(limit).all()]


@router.get('/ingestion/runs/{id}')
def get_ingestion_run(id: int, db: Session = Depends(get_db)):
    item = db.get(IngestionRun, id)
    if not item:
        raise HTTPException(404, 'ingestion run not found')
    return _ingestion_run_detail_out(item, db)


@router.post('/research-notes')
def create_research_note(payload: dict, db: Session = Depends(get_db)):
    data = _normalize_research_note_payload(payload)
    company, hypothesis, evidence = _validate_research_note_refs(data['company_id'], data['hypothesis_id'], data['cited_evidence_ids'], db)
    item = ResearchNote(
        company_id=company.id,
        hypothesis_id=hypothesis.id if hypothesis else None,
        title=data['title'],
        note_type=data['note_type'],
        conclusion_direction=data['conclusion_direction'],
        summary=data['summary'],
        content=data['content'],
        cited_evidence_ids=data['cited_evidence_ids'],
        status=data['status'],
    )
    _update_research_note_counts(item, evidence)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _research_note_detail_out(item, db)


@router.get('/research-notes')
def list_research_notes(company_id: int | None = None, hypothesis_id: int | None = None, note_type: str | None = None, conclusion_direction: str | None = None, status: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50, db: Session = Depends(get_db)):
    _validate_enum_filter('note_type', note_type, RESEARCH_NOTE_TYPES)
    _validate_enum_filter('conclusion_direction', conclusion_direction, RESEARCH_NOTE_DIRECTIONS)
    _validate_enum_filter('status', status, RESEARCH_NOTE_STATUSES)
    query = db.query(ResearchNote)
    if company_id is not None:
        query = query.filter(ResearchNote.company_id == company_id)
    if hypothesis_id is not None:
        query = query.filter(ResearchNote.hypothesis_id == hypothesis_id)
    if note_type:
        query = query.filter(ResearchNote.note_type == note_type)
    if conclusion_direction:
        query = query.filter(ResearchNote.conclusion_direction == conclusion_direction)
    if status:
        query = query.filter(ResearchNote.status == status)
    return [_research_note_out(item, db) for item in query.order_by(ResearchNote.updated_at.desc(), ResearchNote.created_at.desc()).limit(limit).all()]


@router.get('/research-notes/{id}')
def get_research_note(id: int, db: Session = Depends(get_db)):
    item = db.get(ResearchNote, id)
    if not item:
        raise HTTPException(404, 'research note not found')
    return _research_note_detail_out(item, db)


@router.put('/research-notes/{id}')
def update_research_note(id: int, payload: dict, db: Session = Depends(get_db)):
    item = db.get(ResearchNote, id)
    if not item:
        raise HTTPException(404, 'research note not found')
    data = _normalize_research_note_payload(payload, item)
    company, hypothesis, evidence = _validate_research_note_refs(data['company_id'], data['hypothesis_id'], data['cited_evidence_ids'], db)
    item.company_id = company.id
    item.hypothesis_id = hypothesis.id if hypothesis else None
    item.title = data['title']
    item.note_type = data['note_type']
    item.conclusion_direction = data['conclusion_direction']
    item.summary = data['summary']
    item.content = data['content']
    item.cited_evidence_ids = data['cited_evidence_ids']
    item.status = data['status']
    item.updated_at = datetime.utcnow()
    _update_research_note_counts(item, evidence)
    db.commit()
    db.refresh(item)
    return _research_note_detail_out(item, db)


@router.post('/research-notes/{id}/archive')
def archive_research_note(id: int, db: Session = Depends(get_db)):
    item = db.get(ResearchNote, id)
    if not item:
        raise HTTPException(404, 'research note not found')
    item.status = 'archived'
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _research_note_detail_out(item, db)


@router.get('/companies/{id}/report-draft-options')
def company_report_draft_options(id: int, db: Session = Depends(get_db)):
    company = db.get(Company, id)
    if not company:
        raise HTTPException(404, 'company not found')
    hypothesis = _current_hypothesis(company.id, db)
    evidence = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.company_id == company.id).order_by(BusinessLineEvidence.updated_at.desc(), BusinessLineEvidence.created_at.desc()).limit(200).all()
    notes = db.query(ResearchNote).filter(ResearchNote.company_id == company.id).order_by(ResearchNote.updated_at.desc(), ResearchNote.created_at.desc()).limit(200).all()
    return {
        'company': {'id': company.id, 'name': company.name, 'stock_code': company.code, 'industry': company.industry, 'status': company.status},
        'hypothesis': _hypothesis_detail_out(hypothesis, company, db) if hypothesis else None,
        'research_notes': [_research_note_out(item, db) for item in notes],
        'evidence_items': [_evidence_out(item, db) for item in evidence],
    }


@router.post('/report-drafts/preview')
def preview_report_draft(payload: dict, db: Session = Depends(get_db)):
    company_id = payload.get('company_id')
    if company_id is None:
        raise HTTPException(400, 'company_id is required')
    company = db.get(Company, int(company_id))
    if not company:
        raise HTTPException(404, 'company not found')
    note_ids = _unique_int_ids(payload.get('research_note_ids') or [], 'research_note_ids')
    evidence_ids = _unique_int_ids(payload.get('evidence_ids') or [], 'evidence_ids')
    notes = _report_draft_notes(company.id, note_ids, db)
    evidence = _report_draft_evidence(company.id, evidence_ids, db)
    note_evidence_ids = []
    for note in notes:
        note_evidence_ids.extend(note.cited_evidence_ids or [])
    if note_evidence_ids:
        note_evidence = _report_draft_evidence(company.id, note_evidence_ids, db)
        by_id = {item.id: item for item in evidence}
        for item in note_evidence:
            by_id.setdefault(item.id, item)
        evidence = list(by_id.values())
    include_hypothesis = bool(payload.get('include_hypothesis', True))
    include_evidence_trace = bool(payload.get('include_evidence_trace', True))
    include_unreviewed_warning = bool(payload.get('include_unreviewed_warning', True))
    return _report_draft_preview_out(company, notes, evidence, include_hypothesis, include_evidence_trace, include_unreviewed_warning, db)


@router.get('/companies/{id}/discipline-check-options')
def company_discipline_check_options(id: int, db: Session = Depends(get_db)):
    company = db.get(Company, id)
    if not company:
        raise HTTPException(404, 'company not found')
    hypothesis = _current_hypothesis(company.id, db)
    evidence = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.company_id == company.id).order_by(BusinessLineEvidence.updated_at.desc(), BusinessLineEvidence.created_at.desc()).limit(200).all()
    notes = db.query(ResearchNote).filter(ResearchNote.company_id == company.id, ResearchNote.status != 'archived').order_by(ResearchNote.updated_at.desc(), ResearchNote.created_at.desc()).limit(200).all()
    return {
        'company': {'id': company.id, 'name': company.name, 'stock_code': company.code, 'industry': company.industry, 'status': company.status},
        'hypothesis': _hypothesis_detail_out(hypothesis, company, db) if hypothesis else None,
        'research_notes': [_research_note_out(item, db) for item in notes],
        'evidence_items': [_evidence_out(item, db) for item in evidence],
        'checklist_keys': sorted(DISCIPLINE_CHECKLIST_KEYS),
    }


@router.post('/discipline-checks')
def create_discipline_check(payload: dict, db: Session = Depends(get_db)):
    data = _normalize_discipline_check_payload(payload)
    company, hypothesis, evidence, notes = _validate_discipline_check_refs(data, db)
    item = DisciplineCheck(company_id=company.id, hypothesis_id=hypothesis.id if hypothesis else None)
    _apply_discipline_check_data(item, data, evidence, notes)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _discipline_check_detail_out(item, db)


@router.get('/discipline-checks')
def list_discipline_checks(company_id: int | None = None, status: str | None = None, discipline_result: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50, db: Session = Depends(get_db)):
    _validate_enum_filter('status', status, DISCIPLINE_CHECK_STATUSES)
    _validate_enum_filter('discipline_result', discipline_result, DISCIPLINE_RESULTS)
    query = db.query(DisciplineCheck)
    if company_id is not None:
        query = query.filter(DisciplineCheck.company_id == company_id)
    if status:
        query = query.filter(DisciplineCheck.status == status)
    if discipline_result:
        query = query.filter(DisciplineCheck.discipline_result == discipline_result)
    return [_discipline_check_out(item, db) for item in query.order_by(DisciplineCheck.updated_at.desc(), DisciplineCheck.created_at.desc()).limit(limit).all()]


@router.get('/discipline-checks/{id}')
def get_discipline_check(id: int, db: Session = Depends(get_db)):
    item = db.get(DisciplineCheck, id)
    if not item:
        raise HTTPException(404, 'discipline check not found')
    return _discipline_check_detail_out(item, db)


@router.put('/discipline-checks/{id}')
def update_discipline_check(id: int, payload: dict, db: Session = Depends(get_db)):
    item = db.get(DisciplineCheck, id)
    if not item:
        raise HTTPException(404, 'discipline check not found')
    data = _normalize_discipline_check_payload(payload, item)
    company, hypothesis, evidence, notes = _validate_discipline_check_refs(data, db)
    item.company_id = company.id
    item.hypothesis_id = hypothesis.id if hypothesis else None
    _apply_discipline_check_data(item, data, evidence, notes)
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _discipline_check_detail_out(item, db)


@router.post('/discipline-checks/{id}/complete')
def complete_discipline_check(id: int, db: Session = Depends(get_db)):
    item = db.get(DisciplineCheck, id)
    if not item:
        raise HTTPException(404, 'discipline check not found')
    evidence = _discipline_check_evidence_items(item, db)
    notes = _discipline_check_research_note_items(item, db)
    blockers = _discipline_check_blockers(item, evidence, notes, db)
    item.blockers = blockers
    item.discipline_result = 'passed' if not blockers else 'blocked'
    item.updated_at = datetime.utcnow()
    if blockers:
        db.commit()
        raise HTTPException(400, {'message': 'discipline check still has blockers', 'blockers': blockers})
    item.status = 'completed'
    item.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _discipline_check_detail_out(item, db)


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


@router.get('/evidence/{id}')
def get_evidence_detail(id: int, include_raw: bool = False, db: Session = Depends(get_db)):
    item = db.get(BusinessLineEvidence, id)
    if not item:
        raise HTTPException(404, 'evidence not found')
    return _evidence_detail_out(item, db, include_raw)


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
    item = _current_hypothesis(company.id, db)
    return {
        'company_id': company.id,
        'company_name': company.name,
        'stock_code': company.code,
        'hypothesis': _hypothesis_detail_out(item, company, db) if item else None,
    }


@router.put('/companies/{id}/hypotheses')
def upsert_company_hypothesis(id: int, payload: dict, db: Session = Depends(get_db)):
    company = db.get(Company, id)
    if not company:
        raise HTTPException(404, 'company not found')
    data = _normalize_hypothesis_payload(payload)
    item = _current_hypothesis(company.id, db)
    if not item:
        item = InvestmentHypothesis(
            company_id=company.id,
            title=(data['thesis'] or f'{company.name} 核心投资假设待完善')[:120],
            description=data['thesis'],
            related_business_line_ids=[],
            falsification_conditions=data['invalidation_conditions'],
            status='unverified',
            review_status='pending',
            generated_by='manual',
        )
        db.add(item)
    item.thesis = data['thesis']
    item.business_lines = data['business_lines']
    item.watch_metrics = data['watch_metrics']
    item.positive_evidence_rules = data['positive_evidence_rules']
    item.negative_evidence_rules = data['negative_evidence_rules']
    item.invalidation_conditions = data['invalidation_conditions']
    item.current_view = data['current_view']
    item.tracking_priority = data['tracking_priority']
    item.note = data['note']
    item.title = (data['thesis'] or item.title or f'{company.name} 核心投资假设待完善')[:120]
    item.description = data['thesis']
    item.falsification_conditions = data['invalidation_conditions']
    item.generated_by = 'manual'
    item.updated_at = datetime.utcnow()
    company.thesis = data['thesis'] or company.thesis
    company.disproof_conditions = '\n'.join(data['invalidation_conditions']) if data['invalidation_conditions'] else company.disproof_conditions
    db.commit()
    db.refresh(item)
    return {
        'company_id': company.id,
        'company_name': company.name,
        'stock_code': company.code,
        'hypothesis': _hypothesis_detail_out(item, company, db),
    }


@router.get('/companies/{id}/hypothesis-evidence')
def company_hypothesis_evidence(id: int, hypothesis_relation: str | None = None, impact_direction: str | None = None, impact_strength: str | None = None, affected_aspect: str | None = None, review_status: str | None = None, source_name: str | None = None, source_type: str | None = None, has_ingestion_run: bool | None = None, db: Session = Depends(get_db)):
    _validate_enum_filter('hypothesis_relation', hypothesis_relation, HYPOTHESIS_RELATIONS)
    _validate_enum_filter('impact_direction', impact_direction, IMPACT_DIRECTIONS)
    _validate_enum_filter('impact_strength', impact_strength, IMPACT_STRENGTHS)
    _validate_enum_filter('affected_aspect', affected_aspect, AFFECTED_ASPECTS)
    _validate_enum_filter('review_status', review_status, REVIEW_STATUSES)
    if source_type and source_type not in {'announcement', 'news', 'financial', 'manual', 'ai'}:
        raise HTTPException(400, 'source_type has invalid value')
    company = db.get(Company, id)
    if not company:
        raise HTTPException(404, 'company not found')
    hypothesis = _current_hypothesis(company.id, db)
    if not hypothesis:
        return {
            'company_id': company.id,
            'company_name': company.name,
            'hypothesis_id': None,
            'hypothesis_status': 'unknown',
            'summary': _hypothesis_evidence_summary([]),
            'items': [],
        }
    _ensure_hypothesis_evidence_links(company, hypothesis, db)
    items = _company_hypothesis_items(company.id, hypothesis.id, db)
    items = _filter_hypothesis_evidence_items(items, hypothesis_relation, impact_direction, impact_strength, affected_aspect, review_status, source_name, source_type, has_ingestion_run)
    return {
        'company_id': company.id,
        'company_name': company.name,
        'hypothesis_id': hypothesis.id,
        'hypothesis_status': _hypothesis_status(items),
        'summary': _hypothesis_evidence_summary(items),
        'items': [_hypothesis_evidence_item_out(item, db) for item in items],
    }


@router.put('/evidence/{id}/hypothesis-link')
def update_evidence_hypothesis_link(id: int, payload: dict, db: Session = Depends(get_db)):
    item = db.get(BusinessLineEvidence, id)
    if not item:
        raise HTTPException(404, 'evidence not found')
    data = _normalize_hypothesis_link_payload(payload)
    _apply_hypothesis_link(item, data, db)
    db.commit()
    db.refresh(item)
    return _hypothesis_evidence_item_out(item, db)


def _apply_hypothesis_link(item: BusinessLineEvidence, data: dict, db: Session):
    hypothesis_id = data['hypothesis_id']
    if hypothesis_id is None:
        hypothesis = _current_hypothesis(item.company_id, db)
        if not hypothesis:
            raise HTTPException(404, 'hypothesis not found')
    else:
        hypothesis = db.get(InvestmentHypothesis, hypothesis_id)
        if not hypothesis:
            raise HTTPException(404, 'hypothesis not found')
        if hypothesis.company_id != item.company_id:
            raise HTTPException(400, 'hypothesis and evidence must belong to the same company')
    item.hypothesis_id = hypothesis.id
    item.hypothesis_relation = data['hypothesis_relation']
    item.direction = data['impact_direction']
    item.impact_strength = data['impact_strength']
    item.affected_aspect = data['affected_aspect']
    item.evidence_summary = data['evidence_summary']
    item.relation_note = data['relation_note']
    item.updated_at = datetime.utcnow()


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
    pending_count = len([x for x in ev if _normalize_review_status(x.review_status) == 'pending' or x.need_manual_review])
    latest_reviewed = next((x for x in ev if x.reviewed_at), None)
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
            'pending_review_count': len([x for x in line_evidence if _normalize_review_status(x.review_status) == 'pending' or x.need_manual_review]),
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
        'review_status': 'pending' if pending_count else 'approved',
        'review_note': latest_reviewed.review_note if latest_reviewed else None,
        'reviewed_at': latest_reviewed.reviewed_at if latest_reviewed else None,
        'reviewer': latest_reviewed.reviewer if latest_reviewed else None,
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
    pending_evidence = [ev for ev in evidence if _normalize_review_status(ev.review_status) == 'pending']
    primary_review = pending_evidence[0] if pending_evidence else (evidence[0] if evidence else None)
    review_status = _normalize_review_status(primary_review.review_status) if primary_review else ('pending' if item.need_manual_review else 'approved')
    trace = _source_trace_out(item.ingestion_run_id, item.source_name or item.source, getattr(item, 'raw_payload', None), db)
    return {
        'id': item.id,
        'source_type': source_type,
        'evidence_id': primary_review.id if primary_review else None,
        'evidence_detail_url': f'/evidence/{primary_review.id}' if primary_review else None,
        'company_id': item.company_id,
        'company_name': company.name if company else None,
        'stock_code': company.code if company else None,
        'title': item.title,
        'summary': item.summary,
        'source': item.source,
        'source_name': item.source_name or item.source,
        'source_url': item.url,
        'source_date': item.publish_time,
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
        'need_review': item.need_manual_review or any(_normalize_review_status(ev.review_status) == 'pending' for ev in evidence),
        'review_status': review_status,
        'review_item_ids': [ev.id for ev in evidence],
        'review_note': primary_review.review_note if primary_review else None,
        'reviewed_at': primary_review.reviewed_at if primary_review else None,
        'hypothesis_relation': primary_review.hypothesis_relation if primary_review else None,
        'impact_strength': primary_review.impact_strength if primary_review else None,
        'affected_aspect': primary_review.affected_aspect if primary_review else None,
        'related_business_line_names': line_names or (item.related_business_lines or []),
        'publish_time': item.publish_time,
        'fetched_at': item.created_at,
        'ingestion_run_id': item.ingestion_run_id,
        'ingestion_status': trace['ingestion_status'],
        'ingestion_started_at': trace['ingestion_started_at'],
        'ingestion_finished_at': trace['ingestion_finished_at'],
        'is_fallback_source': trace['is_fallback_source'],
        'raw_payload_available': trace['raw_payload_available'],
        'content_hash': item.content_hash,
        'created_at': item.created_at,
    }


def _announcement_out(item: Announcement, db: Session):
    return _feed_item('announcement', item, db)


def _news_out(item: NewsItem, db: Session):
    return _feed_item('news', item, db)


def _financial_out(item: FinancialSnapshot):
    return {'id': item.id, 'company_id': item.company_id, 'stock_code': item.stock_code, 'report_period': item.report_period, 'revenue': _json_number(item.revenue), 'net_profit': _json_number(item.net_profit), 'net_profit_deducted': _json_number(item.net_profit_deducted), 'gross_margin': _json_number(item.gross_margin), 'net_margin': _json_number(item.net_margin), 'operating_cash_flow': _json_number(item.operating_cash_flow), 'accounts_receivable': _json_number(item.accounts_receivable), 'inventory': _json_number(item.inventory), 'debt_asset_ratio': _json_number(item.debt_asset_ratio), 'roe': _json_number(item.roe), 'source': item.source, 'source_name': item.source_name or item.source, 'ingestion_run_id': item.ingestion_run_id, 'created_at': item.created_at, 'updated_at': item.updated_at}


def _job_run_out(item: JobRun):
    return {'id': item.id, 'job_name': item.job_name, 'status': item.status, 'started_at': item.started_at, 'finished_at': item.finished_at, 'result_summary': item.result_summary, 'error_message': item.error_message}


def _json_number(value):
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _evidence_out(item: BusinessLineEvidence, db: Session):
    company = db.get(Company, item.company_id)
    line = db.get(BusinessLine, item.business_line_id) if item.business_line_id else None
    hypothesis = db.get(InvestmentHypothesis, item.hypothesis_id) if item.hypothesis_id else None
    trace = _source_trace_out(item.ingestion_run_id, item.source_name, item.raw_payload, db)
    return {
        'id': item.id,
        'evidence_id': item.id,
        'evidence_detail_url': f'/evidence/{item.id}',
        'stock_code': company.code if company else None,
        'company_id': item.company_id,
        'company_name': company.name if company else None,
        'source_type': item.source_type,
        'source_name': item.source_name,
        'source_id': item.source_id,
        'source_title': item.source_title or item.title,
        'source_url': item.source_url,
        'source_date': item.source_date,
        'ingestion_status': trace['ingestion_status'],
        'ingestion_started_at': trace['ingestion_started_at'],
        'ingestion_finished_at': trace['ingestion_finished_at'],
        'is_fallback_source': trace['is_fallback_source'],
        'raw_payload_available': trace['raw_payload_available'],
        'business_line_id': item.business_line_id,
        'business_line_name': line.name if line else None,
        'hypothesis_id': item.hypothesis_id,
        'hypothesis_title': hypothesis.title if hypothesis else None,
        'evidence_type': item.evidence_type,
        'direction': item.direction,
        'impact_direction': _evidence_impact_direction(item),
        'logic_impact': item.logic_impact,
        'severity': item.severity,
        'title': item.title,
        'summary': item.summary,
        'reason': item.reason,
        'confidence': item.confidence,
        'review_status': _normalize_review_status(item.review_status),
        'need_manual_review': item.need_manual_review,
        'ai_summary': item.ai_summary,
        'ai_impact_judgment': item.ai_impact_judgment,
        'ai_reason': item.ai_reason,
        'ai_confidence': item.ai_confidence,
        'ai_generated_at': item.ai_generated_at,
        'manual_override': item.manual_override,
        'manual_note': item.manual_note,
        'reviewed_at': item.reviewed_at,
        'reviewer': item.reviewer,
        'review_note': item.review_note or item.manual_note,
        'original_content': item.original_content,
        'edited_content': item.edited_content,
        'display_content': item.edited_content or item.summary or item.reason,
        'hypothesis_relation': item.hypothesis_relation or 'watch',
        'impact_strength': item.impact_strength or 'low',
        'affected_aspect': item.affected_aspect or 'other',
        'evidence_summary': item.evidence_summary or item.summary,
        'relation_note': item.relation_note,
        'ingestion_run_id': item.ingestion_run_id,
        'content_hash': item.content_hash,
        'created_at': item.created_at,
        'updated_at': item.updated_at,
    }


def _review_item_out(item: BusinessLineEvidence, db: Session):
    out = _evidence_out(item, db)
    company = db.get(Company, item.company_id)
    hypothesis = _current_hypothesis(item.company_id, db) if company else None
    hypothesis_items = _company_hypothesis_items(company.id, hypothesis.id, db) if company and hypothesis else []
    out.update({
        'type': 'evidence',
        'title': item.title,
        'content': item.edited_content or item.summary or item.reason or item.source_title or item.title,
        'source': item.source_type,
        'source_title': item.source_title or item.title,
        'source_url': item.source_url,
        'company_current_view': hypothesis.current_view if hypothesis else None,
        'company_tracking_priority': hypothesis.tracking_priority if hypothesis else None,
        'hypothesis_status': _hypothesis_status(hypothesis_items) if hypothesis else 'unknown',
    })
    return out


def _evidence_impact_direction(item: BusinessLineEvidence) -> str:
    if item.direction in {'positive', 'negative', 'neutral'}:
        return item.direction
    return {'strengthen': 'positive', 'weaken': 'negative', 'neutral': 'neutral'}.get(item.logic_impact, 'unknown')


def _normalize_review_status(status: str | None) -> str:
    if status == 'confirmed':
        return 'approved'
    if status in REVIEW_STATUSES:
        return status
    return 'pending'


def _review_original_content(item: BusinessLineEvidence) -> str:
    return '\n'.join([
        f'标题：{item.title or ""}',
        f'摘要：{item.summary or ""}',
        f'原因：{item.reason or ""}',
        f'来源：{item.source_title or ""}',
    ]).strip()


def _normalize_research_note_payload(payload: dict, existing: ResearchNote | None = None):
    company_id = payload.get('company_id', existing.company_id if existing else None)
    if company_id is None:
        raise HTTPException(400, 'company_id is required')
    title = str(payload.get('title', existing.title if existing else '') or '').strip()
    if not title:
        raise HTTPException(400, 'title is required')
    note_type = str(payload.get('note_type', existing.note_type if existing else 'manual_note') or 'manual_note').strip()
    direction = str(payload.get('conclusion_direction', existing.conclusion_direction if existing else 'watch') or 'watch').strip()
    status = str(payload.get('status', existing.status if existing else 'active') or 'active').strip()
    if note_type not in RESEARCH_NOTE_TYPES:
        raise HTTPException(400, 'note_type has invalid value')
    if direction not in RESEARCH_NOTE_DIRECTIONS:
        raise HTTPException(400, 'conclusion_direction has invalid value')
    if status not in RESEARCH_NOTE_STATUSES:
        raise HTTPException(400, 'status has invalid value')
    evidence_ids = payload.get('cited_evidence_ids', existing.cited_evidence_ids if existing else [])
    if evidence_ids in (None, ''):
        evidence_ids = []
    if not isinstance(evidence_ids, list):
        raise HTTPException(400, 'cited_evidence_ids must be a list')
    normalized_ids = []
    for evidence_id in evidence_ids:
        try:
            value = int(evidence_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, 'cited_evidence_ids must contain integer ids') from exc
        if value not in normalized_ids:
            normalized_ids.append(value)
    hypothesis_id = payload.get('hypothesis_id', existing.hypothesis_id if existing else None)
    return {
        'company_id': int(company_id),
        'hypothesis_id': int(hypothesis_id) if hypothesis_id not in (None, '') else None,
        'title': title,
        'note_type': note_type,
        'conclusion_direction': direction,
        'summary': str(payload.get('summary', existing.summary if existing else '') or '').strip() or None,
        'content': str(payload.get('content', existing.content if existing else '') or '').strip() or None,
        'cited_evidence_ids': normalized_ids,
        'status': status,
    }


def _validate_research_note_refs(company_id: int, hypothesis_id: int | None, evidence_ids: list[int], db: Session):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, 'company not found')
    hypothesis = db.get(InvestmentHypothesis, hypothesis_id) if hypothesis_id else None
    if hypothesis_id and not hypothesis:
        raise HTTPException(404, 'hypothesis not found')
    if hypothesis and hypothesis.company_id != company.id:
        raise HTTPException(400, 'hypothesis and research note must belong to the same company')
    evidence = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.id.in_(evidence_ids)).all() if evidence_ids else []
    found_ids = {item.id for item in evidence}
    missing = [item for item in evidence_ids if item not in found_ids]
    if missing:
        raise HTTPException(404, f'evidence not found: {missing[0]}')
    mismatched = [item.id for item in evidence if item.company_id != company.id]
    if mismatched:
        raise HTTPException(400, 'cited evidence must belong to the same company')
    return company, hypothesis, evidence


def _update_research_note_counts(item: ResearchNote, evidence: list[BusinessLineEvidence]):
    item.evidence_count = len(evidence)
    item.reviewed_evidence_count = len([row for row in evidence if _normalize_review_status(row.review_status) in {'approved', 'edited'}])
    item.unreviewed_evidence_count = item.evidence_count - item.reviewed_evidence_count


def _research_note_out(item: ResearchNote, db: Session):
    company = db.get(Company, item.company_id)
    return {
        'id': item.id,
        'company_id': item.company_id,
        'company_name': company.name if company else None,
        'stock_code': company.code if company else None,
        'hypothesis_id': item.hypothesis_id,
        'title': item.title,
        'note_type': item.note_type,
        'conclusion_direction': item.conclusion_direction,
        'summary': item.summary,
        'evidence_count': item.evidence_count or 0,
        'reviewed_evidence_count': item.reviewed_evidence_count or 0,
        'unreviewed_evidence_count': item.unreviewed_evidence_count or 0,
        'status': item.status,
        'created_at': item.created_at,
        'updated_at': item.updated_at,
        'research_note_url': f'/research-notes/{item.id}',
    }


def _research_note_detail_out(item: ResearchNote, db: Session):
    out = _research_note_out(item, db)
    hypothesis = db.get(InvestmentHypothesis, item.hypothesis_id) if item.hypothesis_id else None
    evidence = _research_note_evidence_items(item, db)
    _update_research_note_counts(item, evidence)
    out.update({
        'content': item.content,
        'cited_evidence_ids': item.cited_evidence_ids or [],
        'hypothesis': _hypothesis_detail_out(hypothesis, db.get(Company, item.company_id), db) if hypothesis and db.get(Company, item.company_id) else None,
        'cited_evidence_details': [_research_note_evidence_out(row, db) for row in evidence],
    })
    return out


def _research_note_evidence_items(item: ResearchNote, db: Session):
    ids = item.cited_evidence_ids or []
    if not ids:
        return []
    rows = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.id.in_(ids)).all()
    by_id = {row.id: row for row in rows}
    return [by_id[evidence_id] for evidence_id in ids if evidence_id in by_id]


def _research_note_evidence_out(item: BusinessLineEvidence, db: Session):
    return {
        'evidence_id': item.id,
        'title': item.title,
        'summary': item.evidence_summary or item.summary or item.reason,
        'source_name': item.source_name,
        'source_type': item.source_type,
        'source_date': item.source_date,
        'review_status': _normalize_review_status(item.review_status),
        'hypothesis_relation': item.hypothesis_relation or 'watch',
        'impact_direction': _evidence_impact_direction(item),
        'impact_strength': item.impact_strength or 'low',
        'affected_aspect': item.affected_aspect or 'other',
        'evidence_detail_url': f'/evidence/{item.id}',
    }


def _related_research_notes(evidence_id: int, db: Session):
    rows = db.query(ResearchNote).order_by(ResearchNote.updated_at.desc(), ResearchNote.created_at.desc()).limit(500).all()
    result = []
    for item in rows:
        if evidence_id in (item.cited_evidence_ids or []):
            result.append({
                'id': item.id,
                'title': item.title,
                'note_type': item.note_type,
                'conclusion_direction': item.conclusion_direction,
                'status': item.status,
                'research_note_url': f'/research-notes/{item.id}',
            })
    return result


def _unique_int_ids(values, field_name: str):
    if values in (None, ''):
        return []
    if not isinstance(values, list):
        raise HTTPException(400, f'{field_name} must be a list')
    result = []
    for item in values:
        try:
            value = int(item)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f'{field_name} must contain integer ids') from exc
        if value not in result:
            result.append(value)
    return result


def _report_draft_notes(company_id: int, note_ids: list[int], db: Session):
    if not note_ids:
        return []
    notes = db.query(ResearchNote).filter(ResearchNote.id.in_(note_ids)).all()
    by_id = {item.id: item for item in notes}
    for note_id in note_ids:
        item = by_id.get(note_id)
        if not item:
            raise HTTPException(404, f'research note not found: {note_id}')
        if item.company_id != company_id:
            raise HTTPException(400, 'research_note_ids must belong to company_id')
    return [by_id[note_id] for note_id in note_ids]


def _report_draft_evidence(company_id: int, evidence_ids: list[int], db: Session):
    if not evidence_ids:
        return []
    evidence = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.id.in_(evidence_ids)).all()
    by_id = {item.id: item for item in evidence}
    for evidence_id in evidence_ids:
        item = by_id.get(evidence_id)
        if not item:
            raise HTTPException(404, f'evidence not found: {evidence_id}')
        if item.company_id != company_id:
            raise HTTPException(400, 'evidence_ids must belong to company_id')
    return [by_id[evidence_id] for evidence_id in evidence_ids]


def _report_draft_preview_out(company: Company, notes: list[ResearchNote], evidence: list[BusinessLineEvidence], include_hypothesis: bool, include_evidence_trace: bool, include_unreviewed_warning: bool, db: Session):
    hypothesis = _current_hypothesis(company.id, db)
    hypothesis_items = _company_hypothesis_items(company.id, hypothesis.id, db) if hypothesis else []
    reviewed = [item for item in evidence if _normalize_review_status(item.review_status) in {'approved', 'edited'}]
    pending = [item for item in evidence if _normalize_review_status(item.review_status) == 'pending']
    rejected = [item for item in evidence if _normalize_review_status(item.review_status) == 'rejected']
    warnings = []
    if include_unreviewed_warning and pending:
        warnings.append(f'包含 {len(pending)} 条未确认或未复核证据，请谨慎使用。')
    if rejected:
        warnings.append(f'包含 {len(rejected)} 条已驳回证据，不应作为有效依据。')
    if not notes:
        warnings.append('缺少人工研究记录。')
    if not reviewed:
        warnings.append('缺少已确认引用证据。')
    markdown = _build_report_draft_markdown(company, hypothesis, hypothesis_items, notes, evidence, warnings, include_hypothesis, include_evidence_trace, db)
    return {
        'company_id': company.id,
        'company_name': company.name,
        'stock_code': company.code,
        'title': f'{company.name}研究快照',
        'markdown': markdown,
        'summary': {
            'research_note_count': len(notes),
            'evidence_count': len(evidence),
            'reviewed_evidence_count': len(reviewed),
            'unreviewed_evidence_count': len(evidence) - len(reviewed),
            'contains_rejected_evidence': bool(rejected),
        },
        'warnings': warnings,
    }


def _build_report_draft_markdown(company: Company, hypothesis: InvestmentHypothesis | None, hypothesis_items: list[BusinessLineEvidence], notes: list[ResearchNote], evidence: list[BusinessLineEvidence], warnings: list[str], include_hypothesis: bool, include_evidence_trace: bool, db: Session):
    hypothesis_detail = _hypothesis_detail_out(hypothesis, company, db) if hypothesis else None
    lines = [
        f'# {_sanitize_report_text(company.name)} 研究快照',
        '',
        '## 1. 基本信息',
        f'- 股票代码：{_sanitize_report_text(company.code)}',
        f'- 当前结论：{_report_current_view_label(hypothesis_detail.get("current_view") if hypothesis_detail else None)}',
        f'- 跟踪优先级：{_report_priority_label(hypothesis_detail.get("tracking_priority") if hypothesis_detail else None)}',
        f'- 假设验证状态：{_report_hypothesis_status_label(_hypothesis_status(hypothesis_items) if hypothesis else "unknown")}',
        '',
    ]
    if include_hypothesis:
        lines.extend([
            '## 2. 当前投资假设',
            _sanitize_report_text((hypothesis_detail or {}).get('thesis') or '暂无投资假设。'),
            '',
            '### 关键观察指标',
        ])
        watch_metrics = (hypothesis_detail or {}).get('watch_metrics') or []
        lines.extend([f'- {_sanitize_report_text(item)}' for item in watch_metrics] or ['- 暂无。'])
        lines.extend(['', '### 逻辑失效条件'])
        invalidation = (hypothesis_detail or {}).get('invalidation_conditions') or []
        lines.extend([f'- {_sanitize_report_text(item)}' for item in invalidation] or ['- 暂无。'])
        lines.append('')
    lines.extend(['## 3. 研究记录摘要'])
    if notes:
        for note in notes:
            lines.extend([
                f'### {_sanitize_report_text(note.title)}',
                f'- 类型：{_report_note_type_label(note.note_type)}',
                f'- 方向：{_report_conclusion_label(note.conclusion_direction)}',
                f'- 摘要：{_sanitize_report_text(note.summary or "暂无摘要。")}',
                f'- 引用证据数量：{note.evidence_count or 0}',
                f'- 未确认证据数量：{note.unreviewed_evidence_count or 0}',
                f'- 链接：/research-notes/{note.id}',
                '',
            ])
    else:
        lines.extend(['- 暂无研究记录。', ''])
    lines.extend(['## 4. 引用证据'])
    if evidence:
        for item in evidence:
            lines.extend([
                f'### {_sanitize_report_text(item.title)}',
                f'- 复核状态：{_report_review_label(_normalize_review_status(item.review_status))}',
                f'- 假设关系：{_report_relation_label(item.hypothesis_relation)}',
                f'- 影响方向：{_report_impact_label(_evidence_impact_direction(item))}',
                f'- 影响强度：{_report_strength_label(item.impact_strength)}',
                f'- 影响维度：{_report_aspect_label(item.affected_aspect)}',
            ])
            if include_evidence_trace:
                lines.extend([
                    f'- 来源：{_sanitize_report_text(item.source_name or item.source_type or "未记录来源")}',
                    f'- 来源日期：{item.source_date or "-"}',
                ])
            lines.extend([f'- 证据详情：/evidence/{item.id}', ''])
    else:
        lines.extend(['- 暂无引用证据。', ''])
    lines.extend(['## 5. 风险与待观察事项'])
    lines.extend([f'- {_sanitize_report_text(item)}' for item in warnings] or ['- 暂无额外提示。'])
    lines.extend(['', '## 6. 后续观察点'])
    watch_metrics = (hypothesis_detail or {}).get('watch_metrics') or []
    lines.extend([f'- {_sanitize_report_text(item)}' for item in watch_metrics] or ['- 暂无。'])
    lines.extend(['', '> 本草稿仅用于经营跟踪和研究记录整理，不构成任何交易建议。'])
    return _sanitize_report_text('\n'.join(lines))


def _sanitize_report_text(value):
    text = str(value or '')
    replacements = {
        '买入': '[交易动作词已省略]',
        '卖出': '[交易动作词已省略]',
        '加仓': '[交易动作词已省略]',
        '减仓': '[交易动作词已省略]',
        '止损': '[交易动作词已省略]',
        '目标价': '[价格目标词已省略]',
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _report_note_type_label(value):
    return {'daily_note': '日常记录', 'event_review': '事件复盘', 'hypothesis_update': '假设更新', 'risk_review': '风险复核', 'financial_review': '财务复核', 'manual_note': '手动记录'}.get(value, value or '-')


def _report_conclusion_label(value):
    return {'strengthen': '强化假设', 'weaken': '削弱假设', 'watch': '需要观察', 'neutral': '中性', 'risk': '风险提示'}.get(value, value or '-')


def _report_review_label(value):
    return {'pending': '待复核', 'approved': '已确认', 'rejected': '已驳回', 'edited': '已编辑确认'}.get(value, value or '-')


def _report_relation_label(value):
    return {'supports': '支持假设', 'contradicts': '反驳假设', 'neutral': '中性相关', 'watch': '需要观察', 'unrelated': '无关'}.get(value, value or '-')


def _report_impact_label(value):
    return {'positive': '正向', 'negative': '负向', 'neutral': '中性', 'unknown': '未知'}.get(value, value or '-')


def _report_strength_label(value):
    return {'high': '高', 'medium': '中', 'low': '低'}.get(value, value or '-')


def _report_aspect_label(value):
    return {'revenue': '收入', 'profit': '利润', 'margin': '毛利率', 'cashflow': '现金流', 'order': '订单', 'shareholder': '股东行为', 'valuation': '估值', 'industry': '行业', 'policy': '政策', 'risk': '风险', 'business_line': '业务线', 'other': '其他'}.get(value, value or '-')


def _report_current_view_label(value):
    return {'bullish': '偏积极', 'neutral': '中性观察', 'cautious': '谨慎', 'negative': '偏负面'}.get(value, '暂无')


def _report_priority_label(value):
    return {'high': '高', 'medium': '中', 'low': '低'}.get(value, '暂无')


def _report_hypothesis_status_label(value):
    return {'unknown': '证据不足', 'stable': '假设稳定', 'watching': '需要观察', 'risk_rising': '风险上升', 'weakened': '假设削弱'}.get(value, '证据不足')


def _normalize_discipline_check_payload(payload: dict, existing: DisciplineCheck | None = None):
    company_id = payload.get('company_id', existing.company_id if existing else None)
    if company_id is None:
        raise HTTPException(400, 'company_id is required')
    status = str(payload.get('status', existing.status if existing else 'draft') or 'draft').strip()
    if status not in DISCIPLINE_CHECK_STATUSES:
        raise HTTPException(400, 'status has invalid value')
    evidence_ids = _unique_int_ids(payload.get('cited_evidence_ids', existing.cited_evidence_ids if existing else []), 'cited_evidence_ids')
    note_ids = _unique_int_ids(payload.get('cited_research_note_ids', existing.cited_research_note_ids if existing else []), 'cited_research_note_ids')
    hypothesis_id = payload.get('hypothesis_id', existing.hypothesis_id if existing else None)
    checklist_payload = payload.get('checklist', existing.checklist if existing else {})
    if checklist_payload in (None, ''):
        checklist_payload = {}
    if not isinstance(checklist_payload, dict):
        raise HTTPException(400, 'checklist must be an object')
    checklist = {key: bool(checklist_payload.get(key)) for key in DISCIPLINE_CHECKLIST_KEYS}
    raw_pct = payload.get('max_position_pct', existing.max_position_pct if existing else None)
    max_position_pct = None
    if raw_pct not in (None, ''):
        try:
            max_position_pct = float(raw_pct)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, 'max_position_pct must be a number') from exc
        if not math.isfinite(max_position_pct) or max_position_pct <= 0 or max_position_pct > 100:
            raise HTTPException(400, 'max_position_pct must be greater than 0 and no more than 100')
    return {
        'company_id': int(company_id),
        'hypothesis_id': int(hypothesis_id) if hypothesis_id not in (None, '') else None,
        'title': str(payload.get('title', existing.title if existing else '') or '').strip(),
        'status': status,
        'thesis_snapshot': str(payload.get('thesis_snapshot', existing.thesis_snapshot if existing else '') or '').strip(),
        'action_reason': str(payload.get('action_reason', existing.action_reason if existing else '') or '').strip(),
        'position_plan': str(payload.get('position_plan', existing.position_plan if existing else '') or '').strip(),
        'max_position_pct': max_position_pct,
        'risk_acknowledgement': str(payload.get('risk_acknowledgement', existing.risk_acknowledgement if existing else '') or '').strip(),
        'invalidation_plan': str(payload.get('invalidation_plan', existing.invalidation_plan if existing else '') or '').strip(),
        'checklist': checklist,
        'cited_evidence_ids': evidence_ids,
        'cited_research_note_ids': note_ids,
    }


def _validate_discipline_check_refs(data: dict, db: Session):
    company = db.get(Company, data['company_id'])
    if not company:
        raise HTTPException(404, 'company not found')
    hypothesis = db.get(InvestmentHypothesis, data['hypothesis_id']) if data['hypothesis_id'] else _current_hypothesis(company.id, db)
    if data['hypothesis_id'] and not hypothesis:
        raise HTTPException(404, 'hypothesis not found')
    if hypothesis and hypothesis.company_id != company.id:
        raise HTTPException(400, 'hypothesis and discipline check must belong to the same company')
    evidence = _report_draft_evidence(company.id, data['cited_evidence_ids'], db)
    notes = _report_draft_notes(company.id, data['cited_research_note_ids'], db)
    return company, hypothesis, evidence, notes


def _apply_discipline_check_data(item: DisciplineCheck, data: dict, evidence: list[BusinessLineEvidence], notes: list[ResearchNote]):
    item.title = data['title'] or '买入前纪律检查草稿'
    item.status = data['status']
    item.thesis_snapshot = data['thesis_snapshot'] or None
    item.action_reason = data['action_reason'] or None
    item.position_plan = data['position_plan'] or None
    item.max_position_pct = data['max_position_pct']
    item.risk_acknowledgement = data['risk_acknowledgement'] or None
    item.invalidation_plan = data['invalidation_plan'] or None
    item.checklist = data['checklist']
    item.cited_evidence_ids = data['cited_evidence_ids']
    item.cited_research_note_ids = data['cited_research_note_ids']
    item.evidence_count = len(evidence)
    item.reviewed_evidence_count = len([row for row in evidence if _normalize_review_status(row.review_status) in {'approved', 'edited'}])
    item.rejected_evidence_count = len([row for row in evidence if _normalize_review_status(row.review_status) == 'rejected'])
    item.unreviewed_evidence_count = item.evidence_count - item.reviewed_evidence_count
    item.blockers = _discipline_check_blockers(item, evidence, notes, None)
    item.discipline_result = 'passed' if not item.blockers else 'blocked'
    if item.status == 'completed' and item.blockers:
        raise HTTPException(400, {'message': 'discipline check still has blockers', 'blockers': item.blockers})
    if item.status == 'completed' and not item.completed_at:
        item.completed_at = datetime.utcnow()


def _discipline_check_blockers(item: DisciplineCheck, evidence: list[BusinessLineEvidence], notes: list[ResearchNote], db: Session | None):
    blockers = []
    if not item.hypothesis_id:
        blockers.append('缺少结构化投资假设，不能完成纪律检查。')
    required_text = [
        ('thesis_snapshot', '核心逻辑快照不能为空。'),
        ('action_reason', '本次行动理由不能为空。'),
        ('position_plan', '仓位纪律不能为空。'),
        ('risk_acknowledgement', '主要风险确认不能为空。'),
        ('invalidation_plan', '证伪/退出预案不能为空。'),
    ]
    for field, message in required_text:
        if not str(getattr(item, field) or '').strip():
            blockers.append(message)
    if item.max_position_pct is None:
        blockers.append('需要填写最大计划仓位比例。')
    if not evidence:
        blockers.append('至少需要引用一条证据。')
    if evidence and not any(_normalize_review_status(row.review_status) in {'approved', 'edited'} for row in evidence):
        blockers.append('至少需要一条已确认或已编辑确认的证据。')
    pending_count = len([row for row in evidence if _normalize_review_status(row.review_status) == 'pending'])
    if pending_count:
        blockers.append(f'引用证据中仍有 {pending_count} 条待复核证据。')
    rejected_count = len([row for row in evidence if _normalize_review_status(row.review_status) == 'rejected'])
    if rejected_count:
        blockers.append(f'引用证据中包含 {rejected_count} 条已驳回证据。')
    checklist = item.checklist or {}
    checklist_messages = {
        'has_clear_thesis': '尚未确认“核心逻辑清晰”。',
        'evidence_reviewed': '尚未确认“证据已复核”。',
        'risk_reviewed': '尚未确认“主要风险已复核”。',
        'position_within_limit': '尚未确认“仓位符合个人纪律”。',
        'invalidation_defined': '尚未确认“证伪条件和处理预案明确”。',
        'no_pending_key_evidence': '尚未确认“不依赖待复核关键证据”。',
        'no_rejected_core_evidence': '尚未确认“不依赖已驳回核心证据”。',
    }
    for key, message in checklist_messages.items():
        if not checklist.get(key):
            blockers.append(message)
    return blockers


def _discipline_check_out(item: DisciplineCheck, db: Session):
    company = db.get(Company, item.company_id)
    return {
        'id': item.id,
        'company_id': item.company_id,
        'company_name': company.name if company else None,
        'stock_code': company.code if company else None,
        'hypothesis_id': item.hypothesis_id,
        'title': item.title,
        'status': item.status,
        'discipline_result': item.discipline_result,
        'evidence_count': item.evidence_count or 0,
        'reviewed_evidence_count': item.reviewed_evidence_count or 0,
        'unreviewed_evidence_count': item.unreviewed_evidence_count or 0,
        'rejected_evidence_count': item.rejected_evidence_count or 0,
        'blockers': item.blockers or [],
        'max_position_pct': item.max_position_pct,
        'completed_at': item.completed_at,
        'created_at': item.created_at,
        'updated_at': item.updated_at,
        'discipline_check_url': f'/discipline-checks/{item.id}',
    }


def _discipline_check_detail_out(item: DisciplineCheck, db: Session):
    out = _discipline_check_out(item, db)
    evidence = _discipline_check_evidence_items(item, db)
    notes = _discipline_check_research_note_items(item, db)
    hypothesis = db.get(InvestmentHypothesis, item.hypothesis_id) if item.hypothesis_id else None
    company = db.get(Company, item.company_id)
    out.update({
        'thesis_snapshot': item.thesis_snapshot,
        'action_reason': item.action_reason,
        'position_plan': item.position_plan,
        'risk_acknowledgement': item.risk_acknowledgement,
        'invalidation_plan': item.invalidation_plan,
        'checklist': item.checklist or {},
        'cited_evidence_ids': item.cited_evidence_ids or [],
        'cited_research_note_ids': item.cited_research_note_ids or [],
        'hypothesis': _hypothesis_detail_out(hypothesis, company, db) if hypothesis and company else None,
        'cited_evidence_details': [_research_note_evidence_out(row, db) for row in evidence],
        'cited_research_note_details': [_research_note_out(row, db) for row in notes],
    })
    return out


def _discipline_check_evidence_items(item: DisciplineCheck, db: Session):
    ids = item.cited_evidence_ids or []
    if not ids:
        return []
    rows = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.id.in_(ids)).all()
    by_id = {row.id: row for row in rows}
    return [by_id[evidence_id] for evidence_id in ids if evidence_id in by_id]


def _discipline_check_research_note_items(item: DisciplineCheck, db: Session):
    ids = item.cited_research_note_ids or []
    if not ids:
        return []
    rows = db.query(ResearchNote).filter(ResearchNote.id.in_(ids)).all()
    by_id = {row.id: row for row in rows}
    return [by_id[note_id] for note_id in ids if note_id in by_id]


def _reviewed_evidence_without_research_note(db: Session, limit: int = 8):
    cited_ids = set()
    rows = db.query(ResearchNote).filter(ResearchNote.status != 'archived').all()
    for item in rows:
        cited_ids.update(item.cited_evidence_ids or [])
    query = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.review_status.in_(['approved', 'edited']))
    candidates = query.order_by(BusinessLineEvidence.updated_at.desc(), BusinessLineEvidence.created_at.desc()).limit(500).all()
    result = [item for item in candidates if item.id not in cited_ids]
    return result[:limit]


def _evidence_detail_out(item: BusinessLineEvidence, db: Session, include_raw: bool = False):
    company = db.get(Company, item.company_id)
    line = db.get(BusinessLine, item.business_line_id) if item.business_line_id else None
    hypothesis = db.get(InvestmentHypothesis, item.hypothesis_id) if item.hypothesis_id else None
    hypothesis_items = _company_hypothesis_items(company.id, hypothesis.id, db) if company and hypothesis else []
    ingestion_run = db.get(IngestionRun, item.ingestion_run_id) if item.ingestion_run_id else None
    raw_payload = _evidence_raw_payload(item, db)
    trace = _source_trace_out(item.ingestion_run_id, item.source_name, raw_payload, db)
    source_content = _evidence_source_content(item, db)
    return {
        'id': item.id,
        'company': {
            'id': company.id if company else None,
            'name': company.name if company else None,
            'stock_code': company.code if company else None,
        },
        'content': {
            'title': item.title,
            'summary': item.evidence_summary or item.summary,
            'content': item.edited_content or item.summary or item.reason or item.source_title or item.title,
            'reason': item.reason,
            'category': item.source_type,
            'source_date': item.source_date,
            'created_at': item.created_at,
            'updated_at': item.updated_at,
            'source_content': source_content,
        },
        'source_trace': {
            'source_name': item.source_name,
            'source_type': item.source_type,
            'source_url': item.source_url,
            'ingestion_run_id': item.ingestion_run_id,
            'ingestion_status': trace['ingestion_status'],
            'ingestion_started_at': trace['ingestion_started_at'],
            'ingestion_finished_at': trace['ingestion_finished_at'],
            'is_fallback_source': trace['is_fallback_source'],
            'raw_payload_available': bool(raw_payload),
            'content_hash': item.content_hash,
        },
        'review': {
            'review_status': _normalize_review_status(item.review_status),
            'reviewed_at': item.reviewed_at,
            'reviewer': item.reviewer,
            'review_note': item.review_note or item.manual_note,
            'original_content': item.original_content,
            'edited_content': item.edited_content,
        },
        'hypothesis_link': {
            'hypothesis_id': item.hypothesis_id,
            'hypothesis_relation': item.hypothesis_relation or 'watch',
            'impact_direction': _evidence_impact_direction(item),
            'impact_strength': item.impact_strength or 'low',
            'affected_aspect': item.affected_aspect or 'other',
            'evidence_summary': item.evidence_summary or item.summary,
            'relation_note': item.relation_note,
        },
        'hypothesis_context': {
            'hypothesis_status': _hypothesis_status(hypothesis_items) if hypothesis else 'unknown',
            'current_view': hypothesis.current_view if hypothesis else None,
            'tracking_priority': hypothesis.tracking_priority if hypothesis else None,
            'thesis': hypothesis.thesis or hypothesis.description if hypothesis else None,
            'matched_business_line': line.name if line else None,
        },
        'ingestion_run': _ingestion_run_out(ingestion_run, db) if ingestion_run else None,
        'raw_payload': {
            'available': bool(raw_payload),
            'preview': _payload_preview(raw_payload),
            'data': raw_payload if include_raw else None,
        },
        'related_research_notes': _related_research_notes(item.id, db),
        'links': {
            'company_detail': f'/companies/{company.id}' if company else None,
            'ingestion_detail': f'/ingestion?run_id={item.ingestion_run_id}' if item.ingestion_run_id else None,
            'feed': '/feed',
            'review': '/review',
        },
    }


def _evidence_source_content(item: BusinessLineEvidence, db: Session):
    model = {'announcement': Announcement, 'news': NewsItem}.get(item.source_type)
    if not model:
        return None
    source = db.get(model, item.source_id)
    if not source:
        return None
    return {
        'title': source.title,
        'summary': source.summary,
        'raw_text': source.raw_text,
        'url': source.url,
        'source': source.source,
        'source_name': source.source_name,
        'publish_time': source.publish_time,
    }


def _evidence_raw_payload(item: BusinessLineEvidence, db: Session):
    if item.raw_payload:
        return item.raw_payload
    model = {'announcement': Announcement, 'news': NewsItem}.get(item.source_type)
    if model:
        source = db.get(model, item.source_id)
        if source and getattr(source, 'raw_payload', None):
            return source.raw_payload
    if item.source_type == 'financial':
        source = db.get(FinancialSnapshot, item.source_id)
        if source and source.raw_data:
            return source.raw_data
    return None


def _payload_preview(value):
    if not value:
        return None
    text = str(value)
    return text[:1000] + ('...' if len(text) > 1000 else '')


def _sync_source_review_status(item: BusinessLineEvidence, db: Session):
    model = {'announcement': Announcement, 'news': NewsItem}.get(item.source_type)
    if not model:
        return
    source = db.get(model, item.source_id)
    if not source:
        return
    pending_count = db.query(BusinessLineEvidence).filter(
        BusinessLineEvidence.source_type == item.source_type,
        BusinessLineEvidence.source_id == item.source_id,
        BusinessLineEvidence.review_status == 'pending',
    ).count()
    if pending_count == 0:
        source.need_manual_review = False


def _has_hypothesis_link_payload(payload: dict) -> bool:
    return any(key in payload for key in HYPOTHESIS_LINK_FIELDS)


def _hypothesis_out(item: InvestmentHypothesis, db: Session):
    ev = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.hypothesis_id == item.id).all()
    legacy_detail = item.thesis is None and item.business_lines is None and item.watch_metrics is None and item.note is None
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
    latest = ev[0].title if ev else None
    if item.latest_evidence_summary and not db.query(BusinessLineEvidence).filter(BusinessLineEvidence.hypothesis_id == item.id, BusinessLineEvidence.title == item.latest_evidence_summary).first():
        item.latest_evidence_summary = latest
        item.status = status
        db.commit()
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
        'latest_evidence_summary': item.latest_evidence_summary or latest,
        'review_status': _normalize_review_status(item.review_status),
        'created_at': item.created_at,
        'updated_at': item.updated_at,
    }


def _current_hypothesis(company_id: int, db: Session) -> InvestmentHypothesis | None:
    return db.query(InvestmentHypothesis).filter(
        InvestmentHypothesis.company_id == company_id
    ).order_by(InvestmentHypothesis.id.asc()).first()


def _hypothesis_detail_out(item: InvestmentHypothesis, company: Company, db: Session):
    legacy_lines = db.query(BusinessLine).filter(BusinessLine.company_id == company.id).order_by(BusinessLine.id.asc()).all()
    default_payload = _default_hypothesis_payload(company, legacy_lines)
    ev = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.hypothesis_id == item.id).all()
    legacy_detail = item.thesis is None and item.business_lines is None and item.watch_metrics is None and item.note is None
    thesis = item.thesis or item.description or company.thesis or default_payload['thesis']
    business_lines = item.business_lines if isinstance(item.business_lines, list) else default_payload['business_lines']
    watch_metrics = item.watch_metrics if isinstance(item.watch_metrics, list) else default_payload['watch_metrics']
    positive_rules = item.positive_evidence_rules if isinstance(item.positive_evidence_rules, list) else default_payload['positive_evidence_rules']
    negative_rules = item.negative_evidence_rules if isinstance(item.negative_evidence_rules, list) else default_payload['negative_evidence_rules']
    invalidation = item.invalidation_conditions if isinstance(item.invalidation_conditions, list) else (item.falsification_conditions or default_payload['invalidation_conditions'])
    return {
        'id': item.id,
        'company_id': company.id,
        'company_name': company.name,
        'thesis': thesis,
        'business_lines': business_lines,
        'watch_metrics': watch_metrics,
        'positive_evidence_rules': positive_rules,
        'negative_evidence_rules': negative_rules,
        'invalidation_conditions': invalidation,
        'current_view': item.current_view if item.current_view in CURRENT_VIEW_VALUES else default_payload['current_view'],
        'tracking_priority': default_payload['tracking_priority'] if legacy_detail else (item.tracking_priority if item.tracking_priority in TRACKING_PRIORITY_VALUES else default_payload['tracking_priority']),
        'note': item.note or (default_payload['note'] if legacy_detail else None),
        'positive_evidence_count': len([x for x in ev if x.direction == 'positive']),
        'negative_evidence_count': len([x for x in ev if x.direction == 'negative']),
        'risk_evidence_count': len([x for x in ev if x.evidence_type == 'risk']),
        'latest_evidence_summary': item.latest_evidence_summary,
        'hypothesis_status': _hypothesis_status(ev),
        'linked_evidence_count': len(ev),
        'pending_review_count': len([x for x in ev if _normalize_review_status(x.review_status) == 'pending']),
        'updated_at': item.updated_at,
        'created_at': item.created_at,
    }


def _normalize_hypothesis_link_payload(payload: dict):
    relation = str(payload.get('hypothesis_relation') or 'watch').strip()
    direction = str(payload.get('impact_direction') or 'unknown').strip()
    strength = str(payload.get('impact_strength') or 'low').strip()
    aspect = str(payload.get('affected_aspect') or 'other').strip()
    if relation not in HYPOTHESIS_RELATIONS:
        raise HTTPException(400, 'hypothesis_relation must be supports, contradicts, neutral, watch, or unrelated')
    if direction not in IMPACT_DIRECTIONS:
        raise HTTPException(400, 'impact_direction must be positive, negative, neutral, or unknown')
    if strength not in IMPACT_STRENGTHS:
        raise HTTPException(400, 'impact_strength must be high, medium, or low')
    if aspect not in AFFECTED_ASPECTS:
        raise HTTPException(400, 'affected_aspect must be a supported aspect')
    hypothesis_id = payload.get('hypothesis_id')
    return {
        'hypothesis_id': int(hypothesis_id) if hypothesis_id not in (None, '') else None,
        'hypothesis_relation': relation,
        'impact_direction': direction,
        'impact_strength': strength,
        'affected_aspect': aspect,
        'evidence_summary': str(payload.get('evidence_summary') or '').strip() or None,
        'relation_note': str(payload.get('relation_note') or '').strip() or None,
    }


def _hypothesis_evidence_summary(items: list[BusinessLineEvidence]):
    return {
        'supports_count': len([x for x in items if (x.hypothesis_relation or 'watch') == 'supports']),
        'contradicts_count': len([x for x in items if (x.hypothesis_relation or 'watch') == 'contradicts']),
        'watch_count': len([x for x in items if (x.hypothesis_relation or 'watch') == 'watch']),
        'neutral_count': len([x for x in items if (x.hypothesis_relation or 'watch') == 'neutral']),
        'unrelated_count': len([x for x in items if (x.hypothesis_relation or 'watch') == 'unrelated']),
        'pending_review_count': len([x for x in items if _normalize_review_status(x.review_status) == 'pending']),
        'approved_count': len([x for x in items if _normalize_review_status(x.review_status) == 'approved']),
        'rejected_count': len([x for x in items if _normalize_review_status(x.review_status) == 'rejected']),
        'edited_count': len([x for x in items if _normalize_review_status(x.review_status) == 'edited']),
    }


def _hypothesis_status(items: list[BusinessLineEvidence]):
    if not items:
        return 'unknown'
    active = [x for x in items if _normalize_review_status(x.review_status) in {'approved', 'edited'}]
    pending = [x for x in items if _normalize_review_status(x.review_status) == 'pending']
    if not active:
        return 'watching' if pending else 'unknown'
    high_negative = [x for x in active if (x.impact_strength == 'high' and (x.direction == 'negative' or x.hypothesis_relation == 'contradicts'))]
    contradicts = [x for x in active if x.hypothesis_relation == 'contradicts']
    negatives = [x for x in active if x.direction == 'negative']
    supports = [x for x in active if x.hypothesis_relation == 'supports' or x.direction == 'positive']
    watch_or_neutral = [x for x in active if x.hypothesis_relation in {'watch', 'neutral'} or x.direction in {'neutral', 'unknown'}]
    if len(contradicts) >= 2 or len(negatives) >= 2:
        return 'weakened'
    if high_negative:
        return 'risk_rising'
    if supports and not contradicts and not negatives:
        return 'stable'
    if watch_or_neutral or pending:
        return 'watching'
    return 'unknown'


def _hypothesis_evidence_item_out(item: BusinessLineEvidence, db: Session):
    out = _evidence_out(item, db)
    out.update({
        'evidence_id': item.id,
        'content': item.edited_content or item.evidence_summary or item.summary or item.reason or item.title,
        'source': item.source_type,
        'hypothesis_relation': item.hypothesis_relation or 'watch',
        'impact_direction': item.direction if item.direction in IMPACT_DIRECTIONS else 'unknown',
        'impact_strength': item.impact_strength or 'low',
        'affected_aspect': item.affected_aspect or 'other',
        'evidence_summary': item.evidence_summary or item.summary or item.reason,
        'relation_note': item.relation_note,
    })
    return out


def _company_hypothesis_items(company_id: int, hypothesis_id: int, db: Session):
    return db.query(BusinessLineEvidence).filter(
        BusinessLineEvidence.company_id == company_id,
        BusinessLineEvidence.hypothesis_id == hypothesis_id,
    ).order_by(BusinessLineEvidence.source_date.desc(), BusinessLineEvidence.created_at.desc()).all()


def _filter_hypothesis_evidence_items(items: list[BusinessLineEvidence], hypothesis_relation: str | None, impact_direction: str | None, impact_strength: str | None, affected_aspect: str | None, review_status: str | None, source_name: str | None = None, source_type: str | None = None, has_ingestion_run: bool | None = None):
    result = items
    if hypothesis_relation:
        result = [item for item in result if (item.hypothesis_relation or 'watch') == hypothesis_relation]
    if impact_direction:
        result = [item for item in result if (item.direction if item.direction in IMPACT_DIRECTIONS else 'unknown') == impact_direction]
    if impact_strength:
        result = [item for item in result if (item.impact_strength or 'low') == impact_strength]
    if affected_aspect:
        result = [item for item in result if (item.affected_aspect or 'other') == affected_aspect]
    if review_status:
        result = [item for item in result if _normalize_review_status(item.review_status) == review_status]
    if source_name:
        result = [item for item in result if item.source_name == source_name]
    if source_type:
        result = [item for item in result if item.source_type == source_type]
    if has_ingestion_run is True:
        result = [item for item in result if item.ingestion_run_id is not None]
    if has_ingestion_run is False:
        result = [item for item in result if item.ingestion_run_id is None]
    return result


def _source_trace_out(ingestion_run_id: int | None, source_name: str | None, raw_payload, db: Session):
    run = db.get(IngestionRun, ingestion_run_id) if ingestion_run_id else None
    return {
        'ingestion_status': run.status if run else None,
        'ingestion_started_at': run.started_at if run else None,
        'ingestion_finished_at': run.finished_at if run else None,
        'is_fallback_source': source_name == 'local',
        'raw_payload_available': bool(raw_payload) or bool(run and (run.result_summary or run.raw_error)),
    }


def _ingestion_run_detail_out(item: IngestionRun, db: Session):
    out = _ingestion_run_out(item, db)
    announcements = db.query(Announcement).filter(Announcement.ingestion_run_id == item.id).order_by(Announcement.publish_time.desc()).limit(50).all()
    news = db.query(NewsItem).filter(NewsItem.ingestion_run_id == item.id).order_by(NewsItem.publish_time.desc()).limit(50).all()
    evidence = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.ingestion_run_id == item.id).order_by(BusinessLineEvidence.created_at.desc()).limit(50).all()
    feed_items = [_ingestion_feed_item_out('announcement', row, db) for row in announcements]
    feed_items.extend(_ingestion_feed_item_out('news', row, db) for row in news)
    feed_items.sort(key=lambda row: row.get('source_date') or row.get('created_at'), reverse=True)
    out['related_items'] = {
        'feed_items': feed_items,
        'evidence_items': [_ingestion_evidence_item_out(row, db) for row in evidence],
    }
    return out


def _ingestion_feed_item_out(source_type: str, item: Announcement | NewsItem, db: Session):
    company = db.get(Company, item.company_id) if item.company_id else None
    evidence = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.source_type == source_type, BusinessLineEvidence.source_id == item.id).all()
    pending = [row for row in evidence if _normalize_review_status(row.review_status) == 'pending']
    primary = pending[0] if pending else (evidence[0] if evidence else None)
    return {
        'id': item.id,
        'source_type': source_type,
        'evidence_id': primary.id if primary else None,
        'evidence_detail_url': f'/evidence/{primary.id}' if primary else None,
        'company_id': item.company_id,
        'company_name': company.name if company else None,
        'title': item.title,
        'source_date': item.publish_time,
        'review_status': _normalize_review_status(primary.review_status) if primary else ('pending' if item.need_manual_review else 'approved'),
        'hypothesis_relation': primary.hypothesis_relation if primary else None,
        'created_at': item.created_at,
    }


def _ingestion_evidence_item_out(item: BusinessLineEvidence, db: Session):
    company = db.get(Company, item.company_id)
    return {
        'id': item.id,
        'evidence_id': item.id,
        'evidence_detail_url': f'/evidence/{item.id}',
        'company_id': item.company_id,
        'company_name': company.name if company else None,
        'title': item.title,
        'source_type': item.source_type,
        'source_date': item.source_date,
        'review_status': _normalize_review_status(item.review_status),
        'hypothesis_relation': item.hypothesis_relation or 'watch',
    }


def _validate_enum_filter(name: str, value: str | None, allowed: set[str]):
    if value and value not in allowed:
        raise HTTPException(400, f'{name} has invalid value')


def _risk_board_company_out(company: Company, hypothesis: InvestmentHypothesis, items: list[BusinessLineEvidence], status: str):
    active = [item for item in items if _normalize_review_status(item.review_status) != 'rejected']
    negative = [item for item in active if item.direction == 'negative' or item.hypothesis_relation == 'contradicts']
    latest = active[0] if active else None
    return {
        'company_id': company.id,
        'company_name': company.name,
        'stock_code': company.code,
        'hypothesis_status': status,
        'current_view': hypothesis.current_view,
        'tracking_priority': hypothesis.tracking_priority,
        'pending_review_count': len([item for item in items if _normalize_review_status(item.review_status) == 'pending']),
        'negative_evidence_count': len(negative),
        'latest_evidence_title': latest.title if latest else None,
        'latest_evidence_date': latest.source_date or latest.created_at if latest else None,
    }


def _ensure_hypothesis_evidence_links(company: Company, hypothesis: InvestmentHypothesis, db: Session):
    cutoff = datetime.utcnow() - timedelta(days=365)
    items = db.query(BusinessLineEvidence).filter(
        BusinessLineEvidence.company_id == company.id,
        BusinessLineEvidence.hypothesis_id.is_(None),
    ).order_by(BusinessLineEvidence.created_at.desc()).limit(200).all()
    changed = 0
    for item in items:
        source_date = item.source_date or item.created_at
        if source_date and source_date < cutoff:
            continue
        defaults = _default_hypothesis_link(item)
        item.hypothesis_id = hypothesis.id
        item.hypothesis_relation = defaults['hypothesis_relation']
        item.direction = defaults['impact_direction']
        item.impact_strength = defaults['impact_strength']
        item.affected_aspect = defaults['affected_aspect']
        item.evidence_summary = item.evidence_summary or defaults['evidence_summary']
        item.relation_note = item.relation_note or defaults['relation_note']
        changed += 1
    if changed:
        db.commit()


def _default_hypothesis_link(item: BusinessLineEvidence):
    title = item.title or item.source_title or ''
    text = f'{title} {item.summary or ""} {item.reason or ""}'
    if '减持' in text:
        return {
            'hypothesis_relation': 'watch',
            'impact_direction': 'negative',
            'impact_strength': 'medium',
            'affected_aspect': 'shareholder',
            'evidence_summary': '股东减持公告，需要观察其对市场预期和持股信心的影响。',
            'relation_note': '减持本身不直接证伪主营业务逻辑，但属于需要跟踪的偏负面信号。',
        }
    if item.evidence_type == 'risk' or item.direction == 'negative':
        return {
            'hypothesis_relation': 'watch',
            'impact_direction': 'negative',
            'impact_strength': item.severity if item.severity in IMPACT_STRENGTHS else 'medium',
            'affected_aspect': 'risk',
            'evidence_summary': item.summary or item.reason or title,
            'relation_note': '规则识别为风险或负面证据，需要人工复核是否削弱投资假设。',
        }
    if item.direction == 'positive':
        return {
            'hypothesis_relation': 'supports',
            'impact_direction': 'positive',
            'impact_strength': item.severity if item.severity in IMPACT_STRENGTHS else 'low',
            'affected_aspect': 'business_line',
            'evidence_summary': item.summary or title,
            'relation_note': '该证据可能支持当前投资假设，仍需结合后续材料确认持续性。',
        }
    return {
        'hypothesis_relation': 'watch',
        'impact_direction': 'unknown',
        'impact_strength': 'low',
        'affected_aspect': 'other',
        'evidence_summary': item.summary or item.reason or title,
        'relation_note': '相关性或影响方向暂不明确，先纳入观察。',
    }


def _normalize_hypothesis_payload(payload: dict):
    current_view = str(payload.get('current_view') or 'neutral').strip()
    tracking_priority = str(payload.get('tracking_priority') or 'medium').strip()
    if current_view not in CURRENT_VIEW_VALUES:
        raise HTTPException(400, 'current_view must be bullish, neutral, cautious, or negative')
    if tracking_priority not in TRACKING_PRIORITY_VALUES:
        raise HTTPException(400, 'tracking_priority must be high, medium, or low')
    business_lines = payload.get('business_lines')
    if business_lines is None:
        business_lines = []
    if not isinstance(business_lines, list):
        raise HTTPException(400, 'business_lines must be a list')
    clean_lines = []
    for line in business_lines:
        if not isinstance(line, dict):
            raise HTTPException(400, 'business_lines items must be objects')
        importance = str(line.get('importance') or 'medium').strip()
        if importance not in TRACKING_PRIORITY_VALUES:
            raise HTTPException(400, 'business line importance must be high, medium, or low')
        clean_lines.append({
            'name': str(line.get('name') or '').strip(),
            'description': str(line.get('description') or '').strip(),
            'keywords': _clean_string_list(line.get('keywords')),
            'importance': importance,
            'watch_points': _clean_string_list(line.get('watch_points')),
        })
    return {
        'thesis': str(payload.get('thesis') or '').strip(),
        'business_lines': [line for line in clean_lines if line['name']],
        'watch_metrics': _clean_string_list(payload.get('watch_metrics')),
        'positive_evidence_rules': _clean_string_list(payload.get('positive_evidence_rules')),
        'negative_evidence_rules': _clean_string_list(payload.get('negative_evidence_rules')),
        'invalidation_conditions': _clean_string_list(payload.get('invalidation_conditions')),
        'current_view': current_view,
        'tracking_priority': tracking_priority,
        'note': str(payload.get('note') or '').strip() or None,
    }


def _clean_string_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [line.strip('- ').strip() for line in value.split('\n')]
    if not isinstance(value, list):
        raise HTTPException(400, 'JSON list fields must be lists or newline text')
    return [str(item).strip() for item in value if str(item).strip()]


def _default_hypothesis_payload(company: Company, business_lines: list[BusinessLine] | None = None):
    lines = business_lines or []
    if lines:
        line_payload = [{
            'name': line.name,
            'description': line.description or line.role or '待人工完善该业务线说明。',
            'keywords': line.keywords or [],
            'importance': 'high' if line.role == 'core' else 'medium',
            'watch_points': [x.strip() for x in (line.key_metrics or '').split(',') if x.strip()] or ['收入增速', '毛利率', '订单/项目进展'],
        } for line in lines[:5]]
    else:
        line_payload = [
            {'name': '智能座舱', 'description': '座舱域控、显示与交互系统等业务，需人工复核。', 'keywords': ['智能座舱', '域控', '车载显示'], 'importance': 'high', 'watch_points': ['收入增速', '毛利率', '客户定点']},
            {'name': '智能驾驶', 'description': '智能驾驶、辅助驾驶和相关控制器业务，需人工复核。', 'keywords': ['智能驾驶', '自动驾驶', '域控'], 'importance': 'high', 'watch_points': ['新项目定点', '交付进展', '毛利率']},
            {'name': '其他业务', 'description': '其他汽车电子或网联服务相关业务，需后续拆分确认。', 'keywords': ['汽车电子', '网联服务'], 'importance': 'medium', 'watch_points': ['收入贡献', '客户拓展']},
        ]
    return {
        'thesis': company.thesis or f'{company.name} 处于汽车智能化产业链，后续重点跟踪核心业务的订单、收入增速、毛利率和现金流表现。该假设为系统初始化草案，需人工复核。',
        'business_lines': line_payload,
        'watch_metrics': ['营收增速', '毛利率', '归母净利润', '经营现金流', '应收账款', '存货', '新项目定点'],
        'positive_evidence_rules': ['主营业务收入增长', '毛利率改善', '新增重要客户或项目定点', '经营现金流改善'],
        'negative_evidence_rules': ['大股东减持', '毛利率下降', '应收账款或存货异常增加', '经营现金流恶化'],
        'invalidation_conditions': [line.strip('- ').strip() for line in (company.disproof_conditions or '').split('\n') if line.strip()] or ['主营增长逻辑连续两个季度无法验证', '业绩增长主要依赖非经常性损益', '现金流持续恶化', '核心业务竞争力明显削弱'],
        'current_view': 'neutral',
        'tracking_priority': 'high',
        'note': '系统初始化草案，需人工复核。',
    }


def _ensure_company_hypotheses(company: Company, db: Session):
    if db.query(InvestmentHypothesis).filter(InvestmentHypothesis.company_id == company.id).count():
        return
    title = (company.thesis or '').strip().split('\n')[0][:80] or f'{company.name} 核心经营逻辑待验证'
    falsification = [line.strip('- ').strip() for line in (company.disproof_conditions or '').split('\n') if line.strip()]
    if not falsification:
        falsification = ['长期缺少订单、收入、客户或项目落地证据', '财务质量持续转弱或风险事件持续增加']
    line_ids = [line.id for line in db.query(BusinessLine).filter(BusinessLine.company_id == company.id).limit(3).all()]
    defaults = _default_hypothesis_payload(company, db.query(BusinessLine).filter(BusinessLine.company_id == company.id).order_by(BusinessLine.id.asc()).all())
    db.add(InvestmentHypothesis(
        company_id=company.id,
        title=title,
        description=company.thesis or '由公司基础信息自动生成的待验证投资假设，需人工复核。',
        related_business_line_ids=line_ids,
        falsification_conditions=falsification,
        status='unverified',
        review_status='pending',
        generated_by='rule',
        thesis=defaults['thesis'],
        business_lines=defaults['business_lines'],
        watch_metrics=defaults['watch_metrics'],
        positive_evidence_rules=defaults['positive_evidence_rules'],
        negative_evidence_rules=defaults['negative_evidence_rules'],
        invalidation_conditions=defaults['invalidation_conditions'],
        current_view=defaults['current_view'],
        tracking_priority=defaults['tracking_priority'],
        note=defaults['note'],
    ))
    db.commit()


def _review_questions(company: Company, evidence: list[BusinessLineEvidence], risk_count: int):
    pending = [x for x in evidence if _normalize_review_status(x.review_status) == 'pending' or x.need_manual_review]
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
        'review_status': _normalize_review_status(item.review_status),
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


def _logic_company_bucket(impact: str, db: Session, cutoff: datetime | None = None):
    rows = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.logic_impact == impact).order_by(BusinessLineEvidence.created_at.desc()).limit(20).all()
    if cutoff:
        rows = _filter_by_source_date(rows, cutoff)
    return _company_bucket(rows, db)


def _backfill_missing_risk_evidence(db: Session, company_id: int | None = None):
    _normalize_financial_evidence_source_dates(db, company_id)
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


def _normalize_financial_evidence_source_dates(db: Session, company_id: int | None = None):
    query = db.query(BusinessLineEvidence).filter(BusinessLineEvidence.source_type == 'financial')
    if company_id is not None:
        query = query.filter(BusinessLineEvidence.company_id == company_id)
    changed = 0
    for item in query.limit(500).all():
        source = db.get(FinancialSnapshot, item.source_id)
        if not source or not source.report_period:
            continue
        try:
            source_date = datetime.fromisoformat(str(source.report_period))
        except ValueError:
            continue
        if item.source_date != source_date:
            item.source_date = source_date
            changed += 1
    if changed:
        db.commit()


def _filter_by_source_date(items: list[BusinessLineEvidence], cutoff: datetime):
    result = []
    for item in items:
        source_date = item.source_date or item.created_at
        if source_date and source_date >= cutoff:
            result.append(item)
    return result
