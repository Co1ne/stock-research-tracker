from app.core.database import SessionLocal
from app.services.announcement_fetch_service import AnnouncementFetchService


def run_announcement_job():
    db = SessionLocal()
    try:
        return AnnouncementFetchService(db).fetch()
    finally:
        db.close()
