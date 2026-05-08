from datetime import date

from sqlalchemy.orm import Session

from app.data_sources.akshare_provider import AkshareProvider
from app.data_sources.base import AnnouncementDTO, BaseDataSourceAdapter, DataSourceError, DataSourceResult, FinancialSnapshotDTO, NewsDTO
from app.models.models import Announcement, FinancialSnapshot, NewsItem


class AkshareAdapter(BaseDataSourceAdapter):
    name = 'akshare'

    def __init__(self, provider=None):
        self.provider = provider or AkshareProvider()

    def fetch_announcements(self, company, start_date: date | None = None, end_date: date | None = None) -> DataSourceResult:
        try:
            items = self.provider.fetch_announcements(company.code, start_date, end_date)
            return DataSourceResult(self.name, 'announcement', items, {'stock_code': company.code, 'start_date': str(start_date), 'end_date': str(end_date)})
        except Exception as exc:
            return DataSourceResult(self.name, 'announcement', error=DataSourceError(self.name, 'announcement', str(exc), repr(exc)))

    def fetch_news(self, company, keywords: list[str] | None = None, limit: int = 20) -> DataSourceResult:
        try:
            items = self.provider.fetch_company_news(company, keywords or [], limit)
            return DataSourceResult(self.name, 'news', items, {'stock_code': company.code, 'keywords': keywords or [], 'limit': limit})
        except Exception as exc:
            return DataSourceResult(self.name, 'news', error=DataSourceError(self.name, 'news', str(exc), repr(exc)))

    def fetch_financials(self, company) -> DataSourceResult:
        try:
            items = self.provider.fetch_financial_snapshots(company.code)
            return DataSourceResult(self.name, 'financial', items, {'stock_code': company.code})
        except Exception as exc:
            return DataSourceResult(self.name, 'financial', error=DataSourceError(self.name, 'financial', str(exc), repr(exc)))


class LocalAdapter(BaseDataSourceAdapter):
    name = 'local'

    def __init__(self, db: Session):
        self.db = db

    def fetch_announcements(self, company, start_date: date | None = None, end_date: date | None = None) -> DataSourceResult:
        rows = self.db.query(Announcement).filter(Announcement.company_id == company.id).order_by(Announcement.publish_time.desc()).limit(20).all()
        items = [
            AnnouncementDTO(
                stock_code=company.code,
                stock_name=company.name,
                title=row.title,
                publish_time=row.publish_time,
                source='local',
                url=row.url,
                raw_text=row.raw_text,
                summary=row.summary,
                extra={'existing_id': row.id, 'fallback': True},
            )
            for row in rows
        ]
        return DataSourceResult(self.name, 'announcement', items, {'company_id': company.id}, {'fallback': True, 'note': 'local adapter only exposes existing local records'})

    def fetch_news(self, company, keywords: list[str] | None = None, limit: int = 20) -> DataSourceResult:
        rows = self.db.query(NewsItem).filter(NewsItem.company_id == company.id).order_by(NewsItem.publish_time.desc()).limit(limit).all()
        items = [
            NewsDTO(
                title=row.title,
                source='local',
                publish_time=row.publish_time,
                url=row.url,
                summary=row.summary,
                raw_text=row.raw_text,
                related_company=company.name,
                extra={'existing_id': row.id, 'fallback': True},
            )
            for row in rows
        ]
        return DataSourceResult(self.name, 'news', items, {'company_id': company.id, 'limit': limit}, {'fallback': True, 'note': 'local adapter only exposes existing local records'})

    def fetch_financials(self, company) -> DataSourceResult:
        rows = self.db.query(FinancialSnapshot).filter(FinancialSnapshot.company_id == company.id).order_by(FinancialSnapshot.report_period.desc()).limit(8).all()
        items = [
            FinancialSnapshotDTO(
                stock_code=company.code,
                report_period=row.report_period,
                revenue=row.revenue,
                net_profit=row.net_profit,
                net_profit_deducted=row.net_profit_deducted,
                gross_margin=row.gross_margin,
                net_margin=row.net_margin,
                operating_cash_flow=row.operating_cash_flow,
                accounts_receivable=row.accounts_receivable,
                inventory=row.inventory,
                debt_asset_ratio=row.debt_asset_ratio,
                roe=row.roe,
                source='local',
                raw_data={'existing_id': row.id, 'fallback': True},
            )
            for row in rows
        ]
        return DataSourceResult(self.name, 'financial', items, {'company_id': company.id}, {'fallback': True, 'note': 'local adapter only exposes existing local records'})
