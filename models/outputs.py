from pydantic import BaseModel
from typing import Optional


class CheckTokenOutput(BaseModel):
    valid: bool
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    error: Optional[str] = None


class AdAccountOutput(BaseModel):
    account_id: str
    name: str
    account_status: str
    currency: str
    id: str


class ListAdAccountsOutput(BaseModel):
    accounts: list[AdAccountOutput]
    count: int