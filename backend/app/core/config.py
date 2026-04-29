from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'stock-research-tracker'
    database_url: str = 'postgresql+psycopg2://postgres:postgres@db:5432/stock_research'

    ai_enabled: bool = False
    ai_provider: str = 'openai'
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model_fast: str | None = None
    ai_model_strong: str | None = None
    ai_enable_web_search: bool = False

    fetch_announcement_enabled: bool = True
    fetch_news_enabled: bool = True


settings = Settings()
