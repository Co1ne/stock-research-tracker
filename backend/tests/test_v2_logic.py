from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import list_feed, list_reports, list_risks, make_daily_report, mock_news
from app.models.models import Announcement, Base, BusinessLine, BusinessLineEvidence, Company, RiskEvent
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
