import structlog
from fastmcp import FastMCP

from constants import ALERT_BUDGET_THRESHOLD, ALERT_CAC_THRESHOLD
from core.insights import fetch_dashboard
from core.report import summarize_accounts
from models.outputs import (
    AccountSummary,
    ActionLogEntry,
    AlertItem,
    DriftItem,
    GetActionLogOutput,
    GetAlertsOutput,
    GetDriftAnalysisOutput,
    GetReportSnapshotOutput,
)
from persistence.action_log import query_log
from persistence.report_cache import write_cache

report_tools = FastMCP("report-tools")
log = structlog.get_logger()


@report_tools.tool
async def get_alerts(account_ids: list[str] | None = None) -> GetAlertsOutput:
    """Return active rows where CAC or budget exceeds alert thresholds."""
    rows = await fetch_dashboard(account_ids=account_ids)
    alerts: list[AlertItem] = []

    for row in rows:
        today = row["today"]
        cac = today.get("cac")
        budget = row["budget"]

        high_cac = cac is not None and cac > ALERT_CAC_THRESHOLD
        high_budget = budget > ALERT_BUDGET_THRESHOLD

        if not high_cac and not high_budget:
            continue

        if high_cac and high_budget:
            alert_type = "HIGH_CAC_AND_BUDGET"
        elif high_cac:
            alert_type = "HIGH_CAC"
        else:
            alert_type = "HIGH_BUDGET"

        alerts.append(
            AlertItem(
                object_id=row["id"],
                name=row["name"],
                account=row["account"],
                level=row["level"],
                alert_type=alert_type,
                cac=cac,
                budget=budget,
                today_spend=float(today.get("spend", 0)),
            )
        )

    log.info("alerts_fetched", count=len(alerts))
    return GetAlertsOutput(alerts=alerts, count=len(alerts))


@report_tools.tool
async def get_report_snapshot(account_ids: list[str] | None = None) -> GetReportSnapshotOutput:
    """Summarize account performance and persist new cache for drift tracking."""
    result = await summarize_accounts(account_ids=account_ids)
    write_cache(result["new_cache"])

    accounts = [
        AccountSummary(
            account=a["account"],
            spend_today=a["spend_today"],
            spend_yesterday=a["spend_yesterday"],
            spend_day_before=a["spend_day_before"],
            results_today=a["results_today"],
            results_yesterday=a["results_yesterday"],
            total_daily_budget=a["total_daily_budget"],
            est_spend_after_change=a["est_spend_after_change"],
            scale_count=a["scale_count"],
            cut_count=a["cut_count"],
            pause_count=a["pause_count"],
            blended_cac=a["blended_cac"],
        )
        for a in result["accounts"]
    ]

    log.info("report_snapshot_done", accounts=len(accounts))
    return GetReportSnapshotOutput(
        accounts=accounts,
        overall_spend=result["overall_spend"],
        overall_results=result["overall_results"],
        overall_cac=result["overall_cac"],
        overall_budget=result["overall_budget"],
    )


@report_tools.tool
async def get_drift_analysis(account_ids: list[str] | None = None) -> GetDriftAnalysisOutput:
    """Return drift items (IMPROVED/WORSENED/HOLDING) vs previous report cache."""
    result = await summarize_accounts(account_ids=account_ids)

    items = [
        DriftItem(
            object_id=d["object_id"],
            name=d["name"],
            account=d["account"],
            level=d["level"],
            drift=d["drift"],
            prev_cac=d["prev_cac"],
            current_cac=d["current_cac"],
            delta_pct=d["delta_pct"],
        )
        for d in result["drift_items"]
    ]

    log.info("drift_analysis_done", count=len(items))
    return GetDriftAnalysisOutput(items=items, count=len(items))


@report_tools.tool
async def get_action_log(
    date: str | None = None,
    account: str | None = None,
    action_type: str | None = None,
    limit: int = 50,
) -> GetActionLogOutput:
    """Query the SQLite action log. date format: YYYY-MM-DD (IST)."""
    rows = query_log(
        date=date,
        account=account,
        action_type=action_type,
        limit=limit,
    )

    entries = [
        ActionLogEntry(
            id=r["id"],
            timestamp=r["timestamp"],
            account=r.get("account"),
            object_id=r["object_id"],
            level=r["level"],
            name=r.get("name"),
            action=r["action"],
            old_budget=r.get("old_budget"),
            new_budget=r.get("new_budget"),
            cac_at_apply=r.get("cac_at_apply"),
            spend_at_apply=r.get("spend_at_apply"),
            result=r.get("result"),
            dry_run=bool(r.get("dry_run", 0)),
        )
        for r in rows
    ]

    return GetActionLogOutput(entries=entries, count=len(entries))
