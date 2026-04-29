from pydantic import BaseModel


class CompanyBase(BaseModel):
    code: str
    name: str
    market: str = 'A'
    status: str = 'watching'
    holding_cost: float | None = None
    target_price: float | None = None
    thesis: str | None = None
    disproof_conditions: str | None = None
    notes: str | None = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(CompanyBase):
    pass


class CompanyOut(CompanyBase):
    id: int

    class Config:
        from_attributes = True
