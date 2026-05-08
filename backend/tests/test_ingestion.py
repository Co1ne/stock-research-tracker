from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import archive_research_note, company_discipline_check_options, company_hypothesis_evidence, company_report_draft_options, complete_discipline_check, create_discipline_check, create_research_note, dashboard_ingestion_health, dashboard_summary, get_discipline_check, get_evidence_detail, get_ingestion_run, get_research_note, ingest_company, list_discipline_checks, list_feed, list_ingestion_runs, list_research_notes, preview_report_draft, review_decision, review_pending, update_discipline_check, update_evidence_hypothesis_link, update_research_note, upsert_company_hypothesis
from app.data_sources.base import AnnouncementDTO, DataSourceError, DataSourceResult
from app.models.models import Base, BusinessLine, BusinessLineEvidence, Company, IngestionRun, Announcement
from app.services.ingestion_service import IngestionService


def setup_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def seed(db):
    company = Company(code='000001', name='测试公司', status='watching')
    db.add(company)
    db.flush()
    line = BusinessLine(company_id=company.id, name='主营业务', keywords=['订单', '主营'])
    db.add(line)
    db.commit()
    db.refresh(company)
    return company


class FailingAkshareAdapter:
    name = 'akshare'

    def fetch_announcements(self, company, start_date=None, end_date=None):
        return DataSourceResult('akshare', 'announcement', error=DataSourceError('akshare', 'announcement', 'timeout', 'TimeoutError'))

    def fetch_news(self, company, keywords=None, limit=20):
        return DataSourceResult('akshare', 'news', error=DataSourceError('akshare', 'news', 'timeout', 'TimeoutError'))

    def fetch_financials(self, company):
        return DataSourceResult('akshare', 'financial', error=DataSourceError('akshare', 'financial', 'timeout', 'TimeoutError'))


class LocalAnnouncementAdapter:
    name = 'local'

    def __init__(self):
        self.publish_time = datetime(2026, 5, 1, 10, 0, 0)

    def fetch_announcements(self, company, start_date=None, end_date=None):
        return DataSourceResult('local', 'announcement', [
            AnnouncementDTO(
                stock_code=company.code,
                stock_name=company.name,
                title='测试公司获得主营业务订单',
                publish_time=self.publish_time,
                source='local',
                url='https://example.com/a1',
                summary='测试公司获得订单，需人工复核其对经营逻辑的影响。',
                extra={'fixture': True},
            )
        ])

    def fetch_news(self, company, keywords=None, limit=20):
        return DataSourceResult('local', 'news', [])

    def fetch_financials(self, company):
        return DataSourceResult('local', 'financial', [])


class FakeRegistry:
    def __init__(self, adapters):
        self.adapters = adapters

    def ordered_adapters(self):
        return self.adapters


def test_ingest_company_missing_returns_404():
    db = setup_db()
    try:
        ingest_company(999, {'types': ['announcement']}, db=db)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError('missing company should fail')


def test_ingestion_fallback_records_failed_and_success_and_creates_pending_evidence():
    db = setup_db()
    company = seed(db)
    service = IngestionService(db, FakeRegistry([FailingAkshareAdapter(), LocalAnnouncementAdapter()]))

    result = service.ingest_company(company.id, ['announcement'])

    assert result['status'] == 'partial_success'
    runs = db.query(IngestionRun).order_by(IngestionRun.id.asc()).all()
    assert [run.status for run in runs] == ['failed', 'success']
    assert runs[0].source_name == 'akshare'
    assert runs[0].error_message == 'timeout'
    assert runs[1].source_name == 'local'
    evidence = db.query(BusinessLineEvidence).one()
    assert evidence.review_status == 'pending'
    assert evidence.source_name == 'local'
    assert evidence.ingestion_run_id == runs[1].id


def test_ingestion_runs_list_detail_and_health():
    db = setup_db()
    company = seed(db)
    service = IngestionService(db, FakeRegistry([FailingAkshareAdapter(), LocalAnnouncementAdapter()]))
    service.ingest_company(company.id, ['announcement'])

    rows = list_ingestion_runs(company_id=company.id, db=db)
    detail = get_ingestion_run(rows[0]['id'], db=db)
    health = dashboard_ingestion_health(db=db)

    assert len(rows) == 2
    assert detail['request_params'] is not None
    assert health['recent_failed_count'] == 1
    assert any(source['source_name'] == 'local' for source in health['sources'])


def test_ingestion_deduplicates_repeated_collection():
    db = setup_db()
    company = seed(db)
    adapter = LocalAnnouncementAdapter()
    service = IngestionService(db, FakeRegistry([adapter]))

    first = service.ingest_company(company.id, ['announcement'])
    second = service.ingest_company(company.id, ['announcement'])

    assert first['runs'][0]['items_created'] == 1
    assert second['runs'][0]['result_summary']['duplicated'] == 1
    assert db.query(Announcement).count() == 1
    assert db.query(BusinessLineEvidence).count() == 1


def test_feed_review_and_hypothesis_evidence_return_source_trace_fields():
    db = setup_db()
    company = seed(db)
    upsert_company_hypothesis(company.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)
    service = IngestionService(db, FakeRegistry([LocalAnnouncementAdapter()]))
    service.ingest_company(company.id, ['announcement'])

    feed = list_feed(source_name='local', source_type='announcement', review_status='pending', has_ingestion_run=True, db=db)
    pending = review_pending(limit=10, days=0, db=db)
    hypothesis = company_hypothesis_evidence(company.id, source_name='local', source_type='announcement', has_ingestion_run=True, db=db)

    assert len(feed) == 1
    assert feed[0]['source_name'] == 'local'
    assert feed[0]['ingestion_run_id'] is not None
    assert feed[0]['is_fallback_source'] is True
    assert feed[0]['raw_payload_available'] is True
    assert feed[0]['review_status'] == 'pending'
    assert pending[0]['source_name'] == 'local'
    assert pending[0]['ingestion_status'] == 'success'
    assert hypothesis['items'][0]['source_name'] == 'local'
    assert hypothesis['items'][0]['is_fallback_source'] is True


def test_ingestion_detail_returns_related_items():
    db = setup_db()
    company = seed(db)
    service = IngestionService(db, FakeRegistry([LocalAnnouncementAdapter()]))
    service.ingest_company(company.id, ['announcement'])
    run = db.query(IngestionRun).filter(IngestionRun.source_name == 'local').one()

    detail = get_ingestion_run(run.id, db=db)

    assert detail['related_items']['feed_items'][0]['title'] == '测试公司获得主营业务订单'
    assert detail['related_items']['evidence_items'][0]['review_status'] == 'pending'


def test_feed_old_data_without_ingestion_run_is_stable_and_filterable():
    db = setup_db()
    company = seed(db)
    ann = Announcement(company_id=company.id, title='旧公告', publish_time=datetime(2026, 5, 1), source='legacy', need_manual_review=False)
    db.add(ann)
    db.commit()

    all_rows = list_feed(db=db)
    without_run = list_feed(has_ingestion_run=False, db=db)

    assert all_rows[0]['ingestion_run_id'] is None
    assert all_rows[0]['ingestion_status'] is None
    assert without_run[0]['title'] == '旧公告'


def test_evidence_detail_returns_unified_sections_and_raw_on_demand():
    db = setup_db()
    company = seed(db)
    hypothesis = upsert_company_hypothesis(company.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    service = IngestionService(db, FakeRegistry([LocalAnnouncementAdapter()]))
    service.ingest_company(company.id, ['announcement'])
    evidence = db.query(BusinessLineEvidence).one()

    detail = get_evidence_detail(evidence.id, db=db)
    raw_detail = get_evidence_detail(evidence.id, include_raw=True, db=db)

    assert detail['company']['id'] == company.id
    assert detail['content']['title'] == evidence.title
    assert detail['source_trace']['source_name'] == 'local'
    assert detail['source_trace']['is_fallback_source'] is True
    assert detail['review']['review_status'] == 'pending'
    assert detail['hypothesis_link']['hypothesis_relation'] == 'watch'
    assert detail['hypothesis_context']['tracking_priority'] == 'high'
    assert detail['ingestion_run']['status'] == 'success'
    assert detail['raw_payload']['available'] is True
    assert detail['raw_payload']['data'] is None
    assert raw_detail['raw_payload']['data'] is not None
    assert hypothesis['id'] == detail['hypothesis_link']['hypothesis_id']


def test_evidence_detail_missing_and_legacy_without_ingestion_are_stable():
    db = setup_db()
    company = seed(db)
    legacy = BusinessLineEvidence(company_id=company.id, source_type='manual', source_id=1, title='旧证据', review_status='pending')
    db.add(legacy)
    db.commit()
    db.refresh(legacy)

    detail = get_evidence_detail(legacy.id, db=db)

    assert detail['source_trace']['ingestion_run_id'] is None
    assert detail['ingestion_run'] is None
    try:
        get_evidence_detail(999, db=db)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError('missing evidence should fail')


def test_evidence_detail_reflects_link_and_review_updates():
    db = setup_db()
    company = seed(db)
    hypothesis = upsert_company_hypothesis(company.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    service = IngestionService(db, FakeRegistry([LocalAnnouncementAdapter()]))
    service.ingest_company(company.id, ['announcement'])
    evidence = db.query(BusinessLineEvidence).one()

    update_evidence_hypothesis_link(evidence.id, {
        'hypothesis_id': hypothesis['id'],
        'hypothesis_relation': 'supports',
        'impact_direction': 'positive',
        'impact_strength': 'medium',
        'affected_aspect': 'order',
        'evidence_summary': '订单证据支持假设',
        'relation_note': '仍需观察收入确认',
    }, db=db)
    review_decision(evidence.id, {'status': 'approved', 'note': '确认有效'}, db=db)
    detail = get_evidence_detail(evidence.id, db=db)

    assert detail['hypothesis_link']['hypothesis_relation'] == 'supports'
    assert detail['hypothesis_link']['impact_direction'] == 'positive'
    assert detail['review']['review_status'] == 'approved'
    assert detail['review']['review_note'] == '确认有效'


def test_list_items_expose_evidence_detail_url():
    db = setup_db()
    company = seed(db)
    upsert_company_hypothesis(company.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)
    service = IngestionService(db, FakeRegistry([LocalAnnouncementAdapter()]))
    service.ingest_company(company.id, ['announcement'])
    evidence = db.query(BusinessLineEvidence).one()
    run = db.query(IngestionRun).filter(IngestionRun.source_name == 'local').one()

    feed = list_feed(db=db)
    pending = review_pending(limit=10, days=0, db=db)
    hypothesis = company_hypothesis_evidence(company.id, db=db)
    ingestion = get_ingestion_run(run.id, db=db)

    assert feed[0]['evidence_detail_url'] == f'/evidence/{evidence.id}'
    assert pending[0]['evidence_detail_url'] == f'/evidence/{evidence.id}'
    assert hypothesis['items'][0]['evidence_detail_url'] == f'/evidence/{evidence.id}'
    assert ingestion['related_items']['evidence_items'][0]['evidence_detail_url'] == f'/evidence/{evidence.id}'


def make_evidence(db, company, title, review_status='pending', source_id=1):
    item = BusinessLineEvidence(
        company_id=company.id,
        source_type='manual',
        source_id=source_id,
        source_name='manual',
        title=title,
        source_title=title,
        review_status=review_status,
        hypothesis_relation='watch',
        direction='unknown',
        impact_strength='low',
        affected_aspect='other',
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_create_list_and_detail_research_note_with_cited_evidence():
    db = setup_db()
    company = seed(db)
    hypothesis = upsert_company_hypothesis(company.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    approved = make_evidence(db, company, '已确认证据', 'approved', 11)
    pending = make_evidence(db, company, '待复核证据', 'pending', 12)

    created = create_research_note({
        'company_id': company.id,
        'hypothesis_id': hypothesis['id'],
        'title': '事件复盘',
        'note_type': 'event_review',
        'conclusion_direction': 'watch',
        'summary': '需要观察',
        'content': '基于证据形成阶段性判断。',
        'cited_evidence_ids': [approved.id, pending.id],
    }, db=db)
    rows = list_research_notes(company_id=company.id, db=db)
    detail = get_research_note(created['id'], db=db)

    assert created['evidence_count'] == 2
    assert created['reviewed_evidence_count'] == 1
    assert created['unreviewed_evidence_count'] == 1
    assert rows[0]['id'] == created['id']
    assert len(detail['cited_evidence_details']) == 2
    assert detail['cited_evidence_details'][0]['evidence_detail_url'] == f'/evidence/{approved.id}'


def test_research_note_validates_company_evidence_and_enums():
    db = setup_db()
    company = seed(db)
    evidence = make_evidence(db, company, '证据', 'pending', 21)

    for payload, status_code in [
        ({'company_id': 999, 'title': '缺公司', 'cited_evidence_ids': []}, 404),
        ({'company_id': company.id, 'title': '缺证据', 'cited_evidence_ids': [999]}, 404),
        ({'company_id': company.id, 'title': '坏类型', 'note_type': 'bad', 'cited_evidence_ids': [evidence.id]}, 400),
        ({'company_id': company.id, 'title': '坏方向', 'conclusion_direction': 'bad', 'cited_evidence_ids': [evidence.id]}, 400),
    ]:
        try:
            create_research_note(payload, db=db)
        except HTTPException as exc:
            assert exc.status_code == status_code
        else:
            raise AssertionError('invalid research note payload should fail')


def test_update_archive_counts_and_related_research_notes():
    db = setup_db()
    company = seed(db)
    approved = make_evidence(db, company, '已确认', 'approved', 31)
    edited = make_evidence(db, company, '已编辑确认', 'edited', 32)
    rejected = make_evidence(db, company, '已驳回', 'rejected', 33)

    note = create_research_note({
        'company_id': company.id,
        'title': '风险复核',
        'note_type': 'risk_review',
        'conclusion_direction': 'risk',
        'cited_evidence_ids': [approved.id, rejected.id],
    }, db=db)
    updated = update_research_note(note['id'], {
        'company_id': company.id,
        'title': '风险复核更新',
        'note_type': 'risk_review',
        'conclusion_direction': 'watch',
        'status': 'active',
        'cited_evidence_ids': [approved.id, edited.id, rejected.id],
    }, db=db)
    evidence_detail = get_evidence_detail(rejected.id, db=db)
    archived = archive_research_note(note['id'], db=db)

    assert updated['reviewed_evidence_count'] == 2
    assert updated['unreviewed_evidence_count'] == 1
    assert evidence_detail['related_research_notes'][0]['id'] == note['id']
    assert archived['status'] == 'archived'
    assert get_research_note(note['id'], db=db)['cited_evidence_details'][2]['review_status'] == 'rejected'


def test_dashboard_summary_flags_reviewed_evidence_without_research_note():
    db = setup_db()
    company = seed(db)
    noted = make_evidence(db, company, '已沉淀证据', 'approved', 41)
    unnoted = make_evidence(db, company, '待沉淀证据', 'edited', 42)
    create_research_note({
        'company_id': company.id,
        'title': '已沉淀研究记录',
        'note_type': 'manual_note',
        'conclusion_direction': 'neutral',
        'cited_evidence_ids': [noted.id],
    }, db=db)

    summary = dashboard_summary(db=db)

    assert summary['reviewed_evidence_without_note_count'] == 1
    assert summary['reviewed_evidence_without_note'][0]['id'] == unnoted.id


def test_report_draft_preview_generates_markdown_and_warnings():
    db = setup_db()
    company = seed(db)
    upsert_company_hypothesis(company.id, {'thesis': '测试投资假设', 'watch_metrics': ['营收增速'], 'invalidation_conditions': ['现金流持续恶化'], 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)
    approved = make_evidence(db, company, '已确认订单证据', 'approved', 51)
    pending = make_evidence(db, company, '待复核证据', 'pending', 52)
    rejected = make_evidence(db, company, '已驳回证据', 'rejected', 53)
    note = create_research_note({
        'company_id': company.id,
        'title': '事件复盘标题',
        'note_type': 'event_review',
        'conclusion_direction': 'watch',
        'summary': '需要观察',
        'cited_evidence_ids': [approved.id],
    }, db=db)

    result = preview_report_draft({
        'company_id': company.id,
        'research_note_ids': [note['id']],
        'evidence_ids': [pending.id, rejected.id],
        'include_hypothesis': True,
        'include_evidence_trace': True,
        'include_unreviewed_warning': True,
    }, db=db)

    markdown = result['markdown']
    assert company.name in markdown
    assert '测试投资假设' in markdown
    assert '事件复盘标题' in markdown
    assert f'/evidence/{pending.id}' in markdown
    assert result['summary']['research_note_count'] == 1
    assert result['summary']['evidence_count'] == 3
    assert result['summary']['reviewed_evidence_count'] == 1
    assert result['summary']['contains_rejected_evidence'] is True
    assert any('未确认或未复核证据' in item for item in result['warnings'])
    assert any('已驳回证据' in item for item in result['warnings'])
    for banned in ['买入', '卖出', '加仓', '减仓', '止损', '目标价']:
        assert banned not in markdown


def test_report_draft_preview_validates_company_note_and_evidence_ownership():
    db = setup_db()
    company = seed(db)
    other = Company(code='000002', name='其他公司', status='watching')
    db.add(other)
    db.commit()
    db.refresh(other)
    other_evidence = make_evidence(db, other, '其他证据', 'approved', 61)
    other_note = create_research_note({
        'company_id': other.id,
        'title': '其他记录',
        'cited_evidence_ids': [other_evidence.id],
    }, db=db)

    for payload, status_code in [
        ({'company_id': 999}, 404),
        ({'company_id': company.id, 'research_note_ids': [other_note['id']]}, 400),
        ({'company_id': company.id, 'evidence_ids': [other_evidence.id]}, 400),
    ]:
        try:
            preview_report_draft(payload, db=db)
        except HTTPException as exc:
            assert exc.status_code == status_code
        else:
            raise AssertionError('invalid report draft payload should fail')


def test_report_draft_preview_without_notes_or_evidence_and_options():
    db = setup_db()
    company = seed(db)
    upsert_company_hypothesis(company.id, {'thesis': '基础假设', 'current_view': 'neutral', 'tracking_priority': 'medium'}, db=db)

    result = preview_report_draft({'company_id': company.id, 'research_note_ids': [], 'evidence_ids': []}, db=db)
    options = company_report_draft_options(company.id, db=db)

    assert company.name in result['markdown']
    assert result['summary']['research_note_count'] == 0
    assert result['summary']['evidence_count'] == 0
    assert '缺少人工研究记录。' in result['warnings']
    assert '缺少已确认引用证据。' in result['warnings']
    assert options['company']['id'] == company.id
    assert options['hypothesis']['thesis'] == '基础假设'


def discipline_payload(company, hypothesis_id, evidence_ids, note_ids=None):
    return {
        'company_id': company.id,
        'hypothesis_id': hypothesis_id,
        'title': '测试公司买入前纪律检查',
        'thesis_snapshot': '主营业务订单和现金流表现仍需跟踪。',
        'action_reason': '本次行动基于已确认的订单证据和人工研究记录，不依赖未经复核材料。',
        'position_plan': '单一公司最大计划仓位不超过个人纪律上限，分批观察。',
        'max_position_pct': 8,
        'risk_acknowledgement': '已确认现金流、股东行为和业务兑现风险。',
        'invalidation_plan': '若核心业务连续无法验证或现金流持续恶化，则降级观察并复盘。',
        'checklist': {
            'has_clear_thesis': True,
            'evidence_reviewed': True,
            'risk_reviewed': True,
            'position_within_limit': True,
            'invalidation_defined': True,
            'no_pending_key_evidence': True,
            'no_rejected_core_evidence': True,
        },
        'cited_evidence_ids': evidence_ids,
        'cited_research_note_ids': note_ids or [],
    }


def test_create_complete_and_list_discipline_check():
    db = setup_db()
    company = seed(db)
    hypothesis = upsert_company_hypothesis(company.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    evidence = make_evidence(db, company, '已确认证据', 'approved', 71)
    note = create_research_note({'company_id': company.id, 'title': '研究记录', 'cited_evidence_ids': [evidence.id]}, db=db)

    created = create_discipline_check(discipline_payload(company, hypothesis['id'], [evidence.id], [note['id']]), db=db)
    completed = complete_discipline_check(created['id'], db=db)
    rows = list_discipline_checks(company_id=company.id, db=db)
    detail = get_discipline_check(created['id'], db=db)
    options = company_discipline_check_options(company.id, db=db)

    assert created['discipline_result'] == 'passed'
    assert completed['status'] == 'completed'
    assert completed['completed_at'] is not None
    assert rows[0]['id'] == created['id']
    assert detail['cited_evidence_details'][0]['review_status'] == 'approved'
    assert options['hypothesis']['id'] == hypothesis['id']


def test_discipline_check_blocks_pending_and_rejected_evidence():
    db = setup_db()
    company = seed(db)
    hypothesis = upsert_company_hypothesis(company.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    pending = make_evidence(db, company, '待复核证据', 'pending', 81)
    rejected = make_evidence(db, company, '已驳回证据', 'rejected', 82)

    created = create_discipline_check(discipline_payload(company, hypothesis['id'], [pending.id, rejected.id]), db=db)

    assert created['discipline_result'] == 'blocked'
    assert created['rejected_evidence_count'] == 1
    assert any('待复核' in item for item in created['blockers'])
    assert any('已驳回' in item for item in created['blockers'])
    try:
        complete_discipline_check(created['id'], db=db)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert 'blockers' in exc.detail
    else:
        raise AssertionError('blocked discipline check should not complete')


def test_discipline_check_validates_refs_and_enums():
    db = setup_db()
    company = seed(db)
    hypothesis = upsert_company_hypothesis(company.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    evidence = make_evidence(db, company, '已确认证据', 'approved', 91)
    other = Company(code='000003', name='其他公司', status='watching')
    db.add(other)
    db.commit()
    db.refresh(other)
    other_evidence = make_evidence(db, other, '其他证据', 'approved', 92)

    for payload, status_code in [
        ({**discipline_payload(company, hypothesis['id'], [evidence.id]), 'company_id': 999}, 404),
        ({**discipline_payload(company, 999, [evidence.id])}, 404),
        ({**discipline_payload(company, hypothesis['id'], [other_evidence.id])}, 400),
        ({**discipline_payload(company, hypothesis['id'], [evidence.id]), 'status': 'bad'}, 400),
        ({**discipline_payload(company, hypothesis['id'], [evidence.id]), 'max_position_pct': 150}, 400),
    ]:
        try:
            create_discipline_check(payload, db=db)
        except HTTPException as exc:
            assert exc.status_code == status_code
        else:
            raise AssertionError('invalid discipline check payload should fail')


def test_update_discipline_check_recomputes_blockers():
    db = setup_db()
    company = seed(db)
    hypothesis = upsert_company_hypothesis(company.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    pending = make_evidence(db, company, '待复核证据', 'pending', 101)
    approved = make_evidence(db, company, '已确认证据', 'approved', 102)
    created = create_discipline_check(discipline_payload(company, hypothesis['id'], [pending.id]), db=db)

    updated = update_discipline_check(created['id'], discipline_payload(company, hypothesis['id'], [approved.id]), db=db)

    assert created['discipline_result'] == 'blocked'
    assert updated['discipline_result'] == 'passed'
    assert updated['reviewed_evidence_count'] == 1
