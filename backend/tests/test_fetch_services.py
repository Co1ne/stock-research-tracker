from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_sources.base import AnnouncementDTO, FinancialSnapshotDTO, NewsDTO
from app.models.models import Announcement, Base, BusinessLineEvidence, Company, FinancialSnapshot, JobRun, NewsItem, RiskEvent
from app.services.announcement_fetch_service import AnnouncementFetchService
from app.services.financial_fetch_service import FinancialFetchService
from app.services.news_fetch_service import NewsFetchService


def setup_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def seed_company(db):
    company = Company(code='000001', name='测试公司', status='watching')
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


class EmptyAnnouncementProvider:
    def fetch_announcements(self, stock_code, start_date=None, end_date=None):
        return []


class OneAnnouncementProvider:
    def fetch_announcements(self, stock_code, start_date=None, end_date=None):
        return [AnnouncementDTO(stock_code=stock_code, stock_name='测试公司', title='测试公司重大合同公告', publish_time=datetime(2026, 1, 1), source='unit', url='https://example.com/a')]


class FailingAnnouncementProvider:
    def fetch_announcements(self, stock_code, start_date=None, end_date=None):
        raise RuntimeError('provider down')


class NewsProvider:
    def fetch_company_news(self, company, keywords, limit=20):
        return [
            NewsDTO(title='测试公司发布新产品', source='unit', publish_time=datetime.utcnow(), url='https://example.com/n1'),
            NewsDTO(title='无关公司发布消息', source='unit', publish_time=datetime.utcnow(), url='https://example.com/n2'),
        ]


class FinancialProvider:
    def fetch_financial_snapshots(self, stock_code):
        return [FinancialSnapshotDTO(stock_code=stock_code, report_period='2025-12-31', net_profit=100.0, operating_cash_flow=-10.0, source='unit')]


def test_announcement_fetch_handles_empty_result_and_records_job():
    db = setup_db()
    seed_company(db)
    result = AnnouncementFetchService(db, EmptyAnnouncementProvider()).fetch()
    assert result['fetched_companies'] == 1
    assert result['inserted'] == 0
    assert db.query(JobRun).filter(JobRun.job_name == 'fetch_announcements', JobRun.status == 'success').count() == 1


def test_announcement_duplicate_fetch_does_not_insert_twice():
    db = setup_db()
    seed_company(db)
    service = AnnouncementFetchService(db, OneAnnouncementProvider())
    first = service.fetch(record_job=False)
    second = service.fetch(record_job=False)
    assert first['inserted'] == 1
    assert second['duplicated'] == 1
    assert db.query(Announcement).count() == 1


def test_news_relevance_filter_skips_unrelated_items():
    db = setup_db()
    seed_company(db)
    result = NewsFetchService(db, NewsProvider()).fetch(record_job=False)
    assert result['inserted'] == 1
    assert result['skipped_irrelevant'] == 1
    assert db.query(NewsItem).first().title == '测试公司发布新产品'


def test_provider_exception_is_recorded_without_crashing_task():
    db = setup_db()
    seed_company(db)
    result = AnnouncementFetchService(db, FailingAnnouncementProvider()).fetch()
    assert result['failed_companies'][0]['error'] == 'provider down'
    assert db.query(JobRun).filter(JobRun.job_name == 'fetch_announcements', JobRun.status == 'success').count() == 1


def test_financial_fetch_upserts_snapshot():
    db = setup_db()
    company = seed_company(db)
    service = FinancialFetchService(db, FinancialProvider())
    service.fetch(record_job=False)
    service.fetch(record_job=False)
    row = db.query(FinancialSnapshot).filter(FinancialSnapshot.company_id == company.id).one()
    assert row.report_period == '2025-12-31'
    assert row.operating_cash_flow == -10.0


def test_financial_risk_generates_rule_evidence():
    db = setup_db()
    seed_company(db)
    FinancialFetchService(db, FinancialProvider()).fetch(record_job=False)
    risk = db.query(RiskEvent).one()
    evidence = db.query(BusinessLineEvidence).one()
    assert risk.title.endswith('经营现金流与净利润背离')
    assert evidence.evidence_type == 'risk'
    assert evidence.logic_impact == 'weaken'
    assert evidence.review_status == 'pending'
    assert evidence.source_type == 'financial'
