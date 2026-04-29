from app.core.config import settings
from app.data_sources.akshare_provider import AkshareProvider
from app.data_sources.mock_provider import MockProvider


def _provider(name: str):
    if name == 'akshare':
        return AkshareProvider()
    if name == 'mock':
        return MockProvider()
    if name == 'tushare' and not settings.tushare_token:
        raise RuntimeError('DATA_SOURCE selected tushare but TUSHARE_TOKEN is missing')
    raise RuntimeError(f'unsupported data source: {name}')


def announcement_provider():
    return _provider(settings.data_source_announcement)


def news_provider():
    return _provider(settings.data_source_news)


def financial_provider():
    return _provider(settings.data_source_financial)


def market_provider():
    return _provider(settings.data_source_market)


def company_profile_provider():
    return _provider(settings.data_source_financial)
