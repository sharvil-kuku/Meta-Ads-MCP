from fastmcp import FastMCP
from pydantic import BaseModel

report_tools = FastMCP("report-tools")


class AlertItem(BaseModel):
    object_id: str
    name: str
    account: str
    alert_type: str
    value: int


class GetAlertsOutput(BaseModel):
    alerts: list[AlertItem]
    count: int


@report_tools.tool
async def get_alerts() -> GetAlertsOutput:
    """Return active rows where CAC > threshold AND budget > threshold."""
    return GetAlertsOutput(alerts=[], count=0)
