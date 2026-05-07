from fastmcp import FastMCP

from models.inputs import GetActionLogInput, GetAlertsInput, GetDriftAnalysisInput, GetReportSnapshotInput
from models.outputs import (
    GetActionLogOutput,
    GetAlertsOutput,
    GetDriftAnalysisOutput,
    GetReportSnapshotOutput,
)

report_tools = FastMCP("report-tools")


@report_tools.tool
async def get_alerts(input: GetAlertsInput) -> GetAlertsOutput:
    """Return active rows where CAC > threshold AND budget > threshold."""
    return GetAlertsOutput(alerts=[], count=0)


@report_tools.tool
async def get_report_snapshot(input: GetReportSnapshotInput) -> GetReportSnapshotOutput:
    """Summarize account performance; compare to prev report cache for drift."""
    return GetReportSnapshotOutput(accounts=[])


@report_tools.tool
async def get_drift_analysis(input: GetDriftAnalysisInput) -> GetDriftAnalysisOutput:
    """Return drift items (IMPROVED/WORSENED/HOLDING) vs previous report cache."""
    return GetDriftAnalysisOutput(items=[], count=0)


@report_tools.tool
async def get_action_log(input: GetActionLogInput) -> GetActionLogOutput:
    """Query the SQLite action log. date format: YYYY-MM-DD (IST)."""
    return GetActionLogOutput(entries=[], count=0)
