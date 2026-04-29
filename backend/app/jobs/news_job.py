from app.core.database import SessionLocal
from app.services.news_fetch_service import NewsFetchService


def run_news_job():
    db = SessionLocal()
    try:
        return NewsFetchService(db).fetch()
    finally:
        db.close()
