from datetime import datetime

from sqlalchemy.orm import Session

from app.models.models import JobRun


class JobRunService:
    def __init__(self, db: Session):
        self.db = db

    def start(self, job_name: str) -> JobRun:
        run = JobRun(job_name=job_name, status='running', started_at=datetime.utcnow())
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def success(self, run: JobRun, summary: dict):
        run.status = 'success'
        run.finished_at = datetime.utcnow()
        run.result_summary = summary
        self.db.commit()
        self.db.refresh(run)
        return run

    def failed(self, run: JobRun, error: str, summary: dict | None = None):
        run.status = 'failed'
        run.finished_at = datetime.utcnow()
        run.error_message = error
        run.result_summary = summary or {}
        self.db.commit()
        self.db.refresh(run)
        return run
