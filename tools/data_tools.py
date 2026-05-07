from fastmcp import FastMCP
from pydantic import BaseModel

from models.inputs import GetDashboardSnapshotInput, GetInsightsInput

data_tools = FastMCP("data-tools")


class DashboardRow(BaseModel):
    id: str
    name: str
    account: str
    level: str
    status: str
    budget: int = 0
    spend: int = 0
    results: int = 0
    cac: int = 0
    cpi: int = 0


class DashboardSnapshotOutput(BaseModel):
    rows: list[DashboardRow]
    count: int


class InsightsData(BaseModel):
    spend: int = 0
    results: int = 0
    installs: int = 0


class InsightsOutput(BaseModel):
    object_id: str
    today: InsightsData
    yesterday: InsightsData
    day_before: InsightsData


@data_tools.tool
async def get_dashboard_snapshot(input: GetDashboardSnapshotInput) -> DashboardSnapshotOutput:
    """Fetch 3-day insights snapshot for all active campaigns across accounts."""
    return DashboardSnapshotOutput(rows=[], count=0)


@data_tools.tool
async def get_insights(input: GetInsightsInput) -> InsightsOutput:
    """Fetch 3-day insight window (today/yesterday/day-before) for a single campaign or ad set."""
    return InsightsOutput(
        object_id=input.object_id,
        today=InsightsData(),
        yesterday=InsightsData(),
        day_before=InsightsData(),
    )
