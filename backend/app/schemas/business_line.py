from pydantic import BaseModel


class BusinessLineBase(BaseModel):
    company_id: int
    name: str
    role: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    key_metrics: str | None = None
    confidence: str | None = None
    generated_by: str | None = None


class BusinessLineCreate(BusinessLineBase):
    pass


class BusinessLineOut(BusinessLineBase):
    id: int

    class Config:
        from_attributes = True
