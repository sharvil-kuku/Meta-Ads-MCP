from fastmcp import FastMCP

from core.insights import fetch_dashboard, fetch_insights_for_object
from models.inputs import GetDashboardSnapshotInput, GetInsightsInput
from models.outputs import (
    DashboardRow,
    DashboardSnapshotOutput,
    DayInsights,
    InsightsOutput,
)

data_tools = FastMCP("data-tools")


def _day(slot: dict) -> DayInsights:
    return DayInsights(
        spend=slot.get("spend", 0),
        results=slot.get("results", 0),
        installs=slot.get("installs", 0),
        cac=slot.get("cac"),
        cpi=slot.get("cpi"),
    )


@data_tools.tool
async def get_dashboard_snapshot(input: GetDashboardSnapshotInput) -> DashboardSnapshotOutput:
    """Fetch 3-day insights snapshot for all active campaigns and ad sets across accounts."""
    raw_rows = await fetch_dashboard(account_ids=input.account_ids)
    rows = [
        DashboardRow(
            id=r["id"],
            name=r["name"],
            account=r["account"],
            account_id=r["account_id"],
            level=r["level"],
            status=r["status"],
            budget=r["budget"],
            type=r["type"],
            start_time=r.get("start_time"),
            today=_day(r["today"]),
            yesterday=_day(r["yesterday"]),
            day_before=_day(r["day_before"]),
        )
        for r in raw_rows
    ]
    return DashboardSnapshotOutput(rows=rows, count=len(rows))


@data_tools.tool
async def get_insights(input: GetInsightsInput) -> InsightsOutput:
    """Fetch 3-day insight window (today/yesterday/day-before) for a single campaign or ad set."""
    window = await fetch_insights_for_object(input.object_id)
    return InsightsOutput(
        object_id=input.object_id,
        today=_day(window["today"]),
        yesterday=_day(window["yesterday"]),
        day_before=_day(window["day_before"]),
    )
