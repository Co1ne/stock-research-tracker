from fastapi import FastAPI

from app.api.routes import router
from app.core.database import Base, engine
from app.core.schema_compat import ensure_compatible_schema
from app.jobs.scheduler import start_scheduler

app = FastAPI(title='stock-research-tracker')
Base.metadata.create_all(bind=engine)
ensure_compatible_schema(engine)
app.include_router(router)


@app.on_event('startup')
def startup():
    start_scheduler()
