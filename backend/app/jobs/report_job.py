from app.api.routes import make_daily_report
from app.core.database import SessionLocal
from app.services.financial_fetch_service import FinancialFetchService
from app.services.job_run_service import JobRunService


def run_financials_job():
    db = SessionLocal()
    try:
        return FinancialFetchService(db).fetch()
    finally:
        db.close()


def run_daily_report_job():
    db = SessionLocal()
    run = JobRunService(db).start('generate_daily_report')
    try:
        result = make_daily_report(db)
        JobRunService(db).success(run, result)
        return result
    except Exception as exc:
        JobRunService(db).failed(run, str(exc))
        raise
    finally:
        db.close()


def run_weekly_report_job():
    return run_daily_report_job()
