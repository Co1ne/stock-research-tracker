from pydantic import BaseModel, ConfigDict


class CompanyBase(BaseModel):
    code: str
    name: str
    market: str = 'A'
    industry: str | None = None
    main_business: str | None = None
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
    model_config = ConfigDict(from_attributes=True)
