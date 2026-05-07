from pydantic import BaseModel


class CheckTokenInput(BaseModel):
    pass


class ListAdAccountsInput(BaseModel):
    limit: int = 200


class GetDashboardSnapshotInput(BaseModel):
    pass


class GetInsightsInput(BaseModel):
    object_id: str