from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol


@dataclass
class AnnouncementDTO:
    stock_code: str
    stock_name: str | None
    title: str
    publish_time: datetime
    source: str
    url: str | None = None
    raw_text: str | None = None
    summary: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class CompanyProfileDTO:
    stock_code: str
    name: str | None = None
    market: str | None = None
    industry: str | None = None
    main_business: str | None = None
    source: str = 'unknown'
    extra: dict = field(default_factory=dict)


@dataclass
class NewsDTO:
    title: str
    source: str
    publish_time: datetime
    url: str | None = None
    summary: str | None = None
    raw_text: str | None = None
    related_company: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class FinancialSnapshotDTO:
    stock_code: str
    report_period: str
    revenue: float | None = None
    net_profit: float | None = None
    net_profit_deducted: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    operating_cash_flow: float | None = None
    accounts_receivable: float | None = None
    inventory: float | None = None
    debt_asset_ratio: float | None = None
    roe: float | None = None
    source: str = 'unknown'
    raw_data: dict = field(default_factory=dict)


@dataclass
class QuoteDTO:
    stock_code: str
    latest_price: float | None = None
    change_percent: float | None = None
    turnover: float | None = None
    market_value: float | None = None
    source: str = 'unknown'


class AnnouncementProvider(Protocol):
    def fetch_announcements(self, stock_code: str, start_date: date | None, end_date: date | None) -> list[AnnouncementDTO]: ...


class NewsProvider(Protocol):
    def fetch_company_news(self, company, keywords: list[str], limit: int = 20) -> list[NewsDTO]: ...


class FinancialProvider(Protocol):
    def fetch_financial_snapshots(self, stock_code: str) -> list[FinancialSnapshotDTO]: ...


class MarketProvider(Protocol):
    def fetch_latest_quote(self, stock_code: str) -> QuoteDTO | None: ...


class CompanyProfileProvider(Protocol):
    def fetch_company_profile(self, stock_code: str, market: str | None = None) -> CompanyProfileDTO: ...
