from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'stock-research-tracker'
    database_url: str = 'postgresql+psycopg2://postgres:postgres@db:5432/stock_research'

    data_source_announcement: str = 'akshare'
    data_source_news: str = 'akshare'
    data_source_financial: str = 'akshare'
    data_source_market: str = 'akshare'

    fetch_announcement_enabled: bool = True
    fetch_news_enabled: bool = True
    fetch_financial_enabled: bool = True
    fetch_market_enabled: bool = False
    fetch_timeout_seconds: int = 15
    fetch_max_news_per_company: int = 20
    fetch_lookback_days_announcement: int = 30
    fetch_lookback_days_news: int = 7
    financial_risk_recent_periods: int = 8
    scheduler_enabled: bool = True
    report_jobs_enabled: bool = True

    tushare_token: str | None = None

    ai_enabled: bool = False
    ai_provider: str = 'mock'
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model_fast: str | None = None
    ai_model_strong: str | None = None
    ai_prompt_version: str = 'v1'
    ai_auto_analyze_important_items: bool = False
    ai_auto_analyze_importance_threshold: int = 4
    ai_batch_limit_default: int = 20
    ai_enable_web_search: bool = False


settings = Settings()
