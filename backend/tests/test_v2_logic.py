from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fastapi import HTTPException

from app.api.routes import company_hypothesis_evidence, company_hypotheses, dashboard_risk_board, list_feed, list_reports, list_risks, make_daily_report, mock_news, review_decision, review_pending, update_evidence_hypothesis_link, upsert_company_hypothesis
from app.models.models import Announcement, Base, BusinessLine, BusinessLineEvidence, Company, InvestmentHypothesis, RiskEvent
from app.services.business_line_evidence_service import BusinessLineEvidenceService
from app.services.logic_impact_service import LogicImpactService


def setup_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def seed(db):
    c = Company(code='000001', name='测试公司', thesis='订单增长驱动', disproof_conditions='连续亏损')
    db.add(c); db.flush()
    bl = BusinessLine(company_id=c.id, name='智能驾驶', keywords=['智能驾驶', '订单'])
    db.add(bl); db.flush()
    a = Announcement(company_id=c.id, title='获得智能驾驶大订单', raw_text='公司中标重大合同', publish_time=datetime.utcnow(), importance_score=5)
    db.add(a); db.commit(); return c, bl, a


def test_analyze_strengthen_and_write():
    db = setup_db(); _, _, a = seed(db)
    item = LogicImpactService(db).analyze_announcement_logic(a.id)
    assert item.logic_impact == 'strengthen'


def test_generate_evidence_and_dedup():
    db = setup_db(); _, bl, a = seed(db)
    LogicImpactService(db).analyze_announcement_logic(a.id)
    svc = BusinessLineEvidenceService(db)
    n1 = svc.create_evidence_from_announcement(a.id)
    n2 = svc.create_evidence_from_announcement(a.id)
    assert n1 >= 1 and n2 == 0
    rows = db.query(BusinessLineEvidence).all()
    assert any(r.business_line_id == bl.id for r in rows)


def test_ai_fail_fallback_uncertain(monkeypatch):
    db = setup_db(); _, _, a = seed(db)
    svc = LogicImpactService(db)
    monkeypatch.setattr(svc.ai_service, 'analyze_logic_impact', lambda payload: (_ for _ in ()).throw(RuntimeError('boom')))
    item = svc.analyze_announcement_logic(a.id)
    assert item.logic_impact == 'uncertain'


def test_feed_and_risk_list_endpoints():
    db = setup_db(); c, _, _ = seed(db)
    mock_news(c.id, '重大亏损风险', '公司出现重大亏损和诉讼风险', db)

    feed = list_feed(db=db)
    risks = list_risks(db=db)

    assert any(item['source_type'] == 'announcement' for item in feed)
    assert any(item['source_type'] == 'news' for item in feed)
    assert len(risks) == 1
    assert risks[0]['source_type'] == 'news'


def test_report_list_endpoint():
    db = setup_db(); seed(db)
    result = make_daily_report(db)
    reports = list_reports(db=db)

    assert result['report_id']
    assert len(reports) == 1
    assert reports[0]['title'] == '系统周报'


def test_review_pending_and_edited_decision():
    db = setup_db(); c, bl, a = seed(db)
    ev = BusinessLineEvidence(
        company_id=c.id,
        business_line_id=bl.id,
        source_type='announcement',
        source_id=a.id,
        source_title=a.title,
        source_date=a.publish_time,
        evidence_type='risk',
        direction='negative',
        logic_impact='weaken',
        title='现金流质量待复核',
        summary='系统识别到经营风险，需要人工确认。',
        reason='规则命中风险关键词。',
        confidence='rule',
        review_status='pending',
        need_manual_review=True,
    )
    db.add(ev); db.commit(); db.refresh(ev)

    pending = review_pending(limit=50, db=db)
    assert len(pending) == 1
    assert pending[0]['review_status'] == 'pending'

    result = review_decision(ev.id, {'status': 'edited', 'note': '已修正表述', 'edited_content': '人工确认：需继续观察现金流质量。'}, db=db)
    assert result['review_status'] == 'edited'
    assert result['edited_content'] == '人工确认：需继续观察现金流质量。'
    assert result['original_content']
    assert result['review_note'] == '已修正表述'
    assert review_pending(limit=50, db=db) == []


def test_company_hypothesis_missing_is_stable():
    db = setup_db()
    c = Company(code='000002', name='无假设公司')
    db.add(c); db.commit(); db.refresh(c)

    result = company_hypotheses(c.id, db=db)

    assert result['company_id'] == c.id
    assert result['hypothesis'] is None


def test_upsert_and_get_company_hypothesis_detail():
    db = setup_db(); c, _, _ = seed(db)
    payload = {
        'thesis': '智能驾驶业务持续放量，带动长期成长。',
        'business_lines': [{'name': '智能驾驶', 'description': '域控和智驾产品', 'keywords': ['智能驾驶'], 'importance': 'high', 'watch_points': ['订单增速']}],
        'watch_metrics': ['营收增速', '毛利率'],
        'positive_evidence_rules': ['新增头部客户定点'],
        'negative_evidence_rules': ['毛利率持续下滑'],
        'invalidation_conditions': ['核心业务增长证伪'],
        'current_view': 'neutral',
        'tracking_priority': 'high',
        'note': '人工维护的初始投资假设。',
    }

    saved = upsert_company_hypothesis(c.id, payload, db=db)
    loaded = company_hypotheses(c.id, db=db)

    assert saved['hypothesis']['thesis'] == payload['thesis']
    assert loaded['hypothesis']['tracking_priority'] == 'high'
    assert loaded['hypothesis']['business_lines'][0]['importance'] == 'high'
    assert loaded['hypothesis']['watch_metrics'] == ['营收增速', '毛利率']


def test_hypothesis_invalid_enums_are_rejected():
    db = setup_db(); c, _, _ = seed(db)

    try:
        upsert_company_hypothesis(c.id, {'current_view': 'invalid_value'}, db=db)
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError('invalid current_view should fail')

    try:
        upsert_company_hypothesis(c.id, {'tracking_priority': 'urgent'}, db=db)
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError('invalid tracking_priority should fail')


def test_hypothesis_empty_json_fields_are_stable():
    db = setup_db(); c, _, _ = seed(db)
    saved = upsert_company_hypothesis(c.id, {'thesis': '', 'current_view': 'cautious', 'tracking_priority': 'low'}, db=db)
    loaded = company_hypotheses(c.id, db=db)

    assert saved['hypothesis']['business_lines'] == []
    assert loaded['hypothesis']['watch_metrics'] == []
    assert loaded['hypothesis']['current_view'] == 'cautious'


def test_hypothesis_evidence_empty_returns_unknown():
    db = setup_db(); c, _, _ = seed(db)
    upsert_company_hypothesis(c.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'medium'}, db=db)

    result = company_hypothesis_evidence(c.id, db=db)

    assert result['hypothesis_status'] == 'unknown'
    assert result['summary']['supports_count'] == 0
    assert result['items'] == []


def test_update_evidence_hypothesis_link_and_status():
    db = setup_db(); c, bl, a = seed(db)
    hypothesis = upsert_company_hypothesis(c.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    ev = BusinessLineEvidence(
        company_id=c.id,
        business_line_id=bl.id,
        source_type='announcement',
        source_id=a.id,
        source_title=a.title,
        source_date=a.publish_time,
        evidence_type='risk',
        direction='negative',
        logic_impact='weaken',
        title='负面高影响证据',
        summary='高影响负面证据',
        reason='测试',
        confidence='rule',
        review_status='approved',
    )
    db.add(ev); db.commit(); db.refresh(ev)

    updated = update_evidence_hypothesis_link(ev.id, {
        'hypothesis_id': hypothesis['id'],
        'hypothesis_relation': 'contradicts',
        'impact_direction': 'negative',
        'impact_strength': 'high',
        'affected_aspect': 'cashflow',
        'evidence_summary': '现金流风险较强。',
        'relation_note': '已确认负面证据。',
    }, db=db)
    result = company_hypothesis_evidence(c.id, db=db)

    assert updated['hypothesis_relation'] == 'contradicts'
    assert updated['impact_strength'] == 'high'
    assert result['hypothesis_status'] == 'risk_rising'
    assert result['summary']['approved_count'] == 1


def test_hypothesis_link_invalid_enums_are_rejected():
    db = setup_db(); c, bl, a = seed(db)
    ev = BusinessLineEvidence(company_id=c.id, business_line_id=bl.id, source_type='announcement', source_id=a.id, title='证据', review_status='pending')
    db.add(ev); db.commit(); db.refresh(ev)

    invalid_cases = [
        {'hypothesis_relation': 'bad'},
        {'impact_direction': 'bad'},
        {'impact_strength': 'bad'},
        {'affected_aspect': 'bad'},
    ]
    for payload in invalid_cases:
        try:
            update_evidence_hypothesis_link(ev.id, payload, db=db)
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f'{payload} should fail')


def test_rejected_evidence_does_not_drive_hypothesis_status_and_review_stats_update():
    db = setup_db(); c, bl, a = seed(db)
    hypothesis = upsert_company_hypothesis(c.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    ev = BusinessLineEvidence(
        company_id=c.id,
        business_line_id=bl.id,
        source_type='announcement',
        source_id=a.id,
        title='待复核负面证据',
        summary='待复核',
        review_status='pending',
    )
    db.add(ev); db.commit(); db.refresh(ev)
    update_evidence_hypothesis_link(ev.id, {
        'hypothesis_id': hypothesis['id'],
        'hypothesis_relation': 'contradicts',
        'impact_direction': 'negative',
        'impact_strength': 'high',
        'affected_aspect': 'risk',
    }, db=db)

    pending_result = company_hypothesis_evidence(c.id, db=db)
    review_decision(ev.id, {'status': 'rejected', 'note': '不采纳'}, db=db)
    rejected_result = company_hypothesis_evidence(c.id, db=db)

    assert pending_result['summary']['pending_review_count'] == 1
    assert pending_result['hypothesis_status'] == 'watching'
    assert rejected_result['summary']['rejected_count'] == 1
    assert rejected_result['hypothesis_status'] == 'unknown'


def test_review_pending_returns_hypothesis_relation_fields():
    db = setup_db(); c, bl, a = seed(db)
    hypothesis = upsert_company_hypothesis(c.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    ev = BusinessLineEvidence(company_id=c.id, business_line_id=bl.id, hypothesis_id=hypothesis['id'], source_type='announcement', source_id=a.id, title='待复核证据', review_status='pending', hypothesis_relation='watch', direction='negative', impact_strength='medium', affected_aspect='shareholder')
    db.add(ev); db.commit()

    result = review_pending(limit=10, db=db)

    assert result[0]['hypothesis_relation'] == 'watch'
    assert result[0]['impact_direction'] == 'negative'
    assert result[0]['company_tracking_priority'] == 'high'
    assert result[0]['hypothesis_status'] == 'watching'


def test_review_decision_can_update_relation_fields_and_reject_invalid_relation():
    db = setup_db(); c, bl, a = seed(db)
    hypothesis = upsert_company_hypothesis(c.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    ev = BusinessLineEvidence(company_id=c.id, business_line_id=bl.id, source_type='announcement', source_id=a.id, title='订单证据', review_status='pending')
    db.add(ev); db.commit(); db.refresh(ev)

    result = review_decision(ev.id, {'status': 'approved', 'note': '确认', 'hypothesis_id': hypothesis['id'], 'hypothesis_relation': 'supports', 'impact_direction': 'positive', 'impact_strength': 'medium', 'affected_aspect': 'order', 'evidence_summary': '新增订单支持假设', 'relation_note': '仍需观察收入确认'}, db=db)
    assert result['review_status'] == 'approved'
    assert result['hypothesis_relation'] == 'supports'
    assert result['impact_direction'] == 'positive'

    ev2 = BusinessLineEvidence(company_id=c.id, business_line_id=bl.id, source_type='announcement', source_id=a.id + 100, title='坏枚举证据', review_status='pending')
    db.add(ev2); db.commit(); db.refresh(ev2)
    try:
        review_decision(ev2.id, {'status': 'approved', 'hypothesis_relation': 'bad'}, db=db)
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError('invalid relation should fail')


def test_dashboard_risk_board_buckets_and_missing_evidence():
    db = setup_db()
    c1, bl1, a1 = seed(db)
    h1 = upsert_company_hypothesis(c1.id, {'thesis': '风险假设', 'current_view': 'cautious', 'tracking_priority': 'high'}, db=db)['hypothesis']
    ev1 = BusinessLineEvidence(company_id=c1.id, business_line_id=bl1.id, hypothesis_id=h1['id'], source_type='announcement', source_id=a1.id, title='高影响负面', review_status='approved', hypothesis_relation='contradicts', direction='negative', impact_strength='high', affected_aspect='risk')
    db.add(ev1)
    c2 = Company(code='000003', name='证据不足公司')
    db.add(c2); db.flush()
    upsert_company_hypothesis(c2.id, {'thesis': '高优先级待验证', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)
    c3 = Company(code='000004', name='假设削弱公司')
    db.add(c3); db.flush()
    bl3 = BusinessLine(company_id=c3.id, name='主营业务', keywords=['主营'])
    db.add(bl3); db.flush()
    h3 = upsert_company_hypothesis(c3.id, {'thesis': '增长假设', 'current_view': 'negative', 'tracking_priority': 'high'}, db=db)['hypothesis']
    ev3 = BusinessLineEvidence(company_id=c3.id, business_line_id=bl3.id, hypothesis_id=h3['id'], source_type='manual', source_id=3001, title='负面证据一', review_status='approved', hypothesis_relation='contradicts', direction='negative', impact_strength='medium', affected_aspect='profit')
    ev4 = BusinessLineEvidence(company_id=c3.id, business_line_id=bl3.id, hypothesis_id=h3['id'], source_type='manual', source_id=3002, title='负面证据二', review_status='edited', hypothesis_relation='contradicts', direction='negative', impact_strength='low', affected_aspect='cashflow')
    db.add_all([ev3, ev4])
    db.commit()

    result = dashboard_risk_board(db=db)

    assert result['review']['approved_count'] >= 1
    assert any(item['company_id'] == c1.id for item in result['risk_companies'])
    assert any(item['company_id'] == c3.id for item in result['weakened_companies'])
    assert any(item['company_id'] == c2.id for item in result['missing_evidence_companies'])


def test_hypothesis_evidence_filters_and_invalid_filter():
    db = setup_db(); c, bl, a = seed(db)
    hypothesis = upsert_company_hypothesis(c.id, {'thesis': '测试假设', 'current_view': 'neutral', 'tracking_priority': 'high'}, db=db)['hypothesis']
    ev = BusinessLineEvidence(company_id=c.id, business_line_id=bl.id, hypothesis_id=hypothesis['id'], source_type='announcement', source_id=a.id, title='观察证据', review_status='pending', hypothesis_relation='watch', direction='negative', impact_strength='medium', affected_aspect='shareholder')
    db.add(ev); db.commit()

    result = company_hypothesis_evidence(c.id, hypothesis_relation='watch', impact_direction='negative', impact_strength='medium', affected_aspect='shareholder', review_status='pending', db=db)
    assert len(result['items']) == 1
    assert result['summary']['watch_count'] == 1

    try:
        company_hypothesis_evidence(c.id, hypothesis_relation='bad', db=db)
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError('invalid filter should fail')
