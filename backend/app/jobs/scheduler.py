from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.jobs.announcement_job import run_announcement_job
from app.jobs.news_job import run_news_job
from app.jobs.report_job import run_daily_report_job, run_financials_job, run_weekly_report_job

scheduler = BackgroundScheduler(timezone='Asia/Shanghai')


def configure_scheduler():
    if settings.fetch_announcement_enabled:
        for hour, minute in [(9, 0), (12, 30), (16, 30), (21, 30)]:
            scheduler.add_job(run_announcement_job, 'cron', hour=hour, minute=minute, id=f'fetch_announcements_{hour}_{minute}', replace_existing=True, max_instances=1)
    if settings.fetch_news_enabled:
        for hour, minute in [(9, 10), (12, 40), (16, 40), (21, 40)]:
            scheduler.add_job(run_news_job, 'cron', hour=hour, minute=minute, id=f'fetch_news_{hour}_{minute}', replace_existing=True, max_instances=1)
    if settings.fetch_financial_enabled:
        scheduler.add_job(run_financials_job, 'cron', hour=22, minute=0, id='fetch_financials_daily', replace_existing=True, max_instances=1)
    if settings.report_jobs_enabled:
        scheduler.add_job(run_daily_report_job, 'cron', hour=22, minute=30, id='generate_daily_report', replace_existing=True, max_instances=1)
        scheduler.add_job(run_weekly_report_job, 'cron', day_of_week='sun', hour=22, minute=30, id='generate_weekly_report', replace_existing=True, max_instances=1)


def start_scheduler():
    if not settings.scheduler_enabled:
        return
    if not scheduler.running:
        configure_scheduler()
        scheduler.start()
