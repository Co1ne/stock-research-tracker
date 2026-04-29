from app.data_sources.base import AnnouncementDTO, CompanyProfileDTO, FinancialSnapshotDTO, NewsDTO, QuoteDTO


class MockProvider:
    def fetch_company_profile(self, stock_code, market=None) -> CompanyProfileDTO:
        return CompanyProfileDTO(stock_code=stock_code, name=None, market=market or 'A', source='mock')

    def fetch_announcements(self, stock_code, start_date=None, end_date=None) -> list[AnnouncementDTO]:
        return []

    def fetch_company_news(self, company, keywords: list[str], limit: int = 20) -> list[NewsDTO]:
        return []

    def fetch_financial_snapshots(self, stock_code: str) -> list[FinancialSnapshotDTO]:
        return []

    def fetch_latest_quote(self, stock_code: str) -> QuoteDTO | None:
        return None
