from fastapi import FastAPI

from app.api.routes import router
from app.core.database import Base, engine

app = FastAPI(title='stock-research-tracker')
Base.metadata.create_all(bind=engine)
app.include_router(router)
