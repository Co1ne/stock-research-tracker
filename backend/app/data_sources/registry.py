from sqlalchemy.orm import Session

from app.data_sources.adapters import AkshareAdapter, LocalAdapter


class DataSourceRegistry:
    def __init__(self, db: Session, adapters=None):
        self.db = db
        self.adapters = adapters

    def ordered_adapters(self):
        if self.adapters is not None:
            return self.adapters
        return [AkshareAdapter(), LocalAdapter(self.db)]
