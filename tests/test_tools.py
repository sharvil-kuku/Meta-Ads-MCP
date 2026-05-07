"""Integration tests for all 14 MCP tools — external calls mocked."""
import json
import os
from unittest.mock import AsyncMock, patch

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_insights.json")
with open(_FIXTURE_PATH) as f:
    SAMPLE_ROWS = json.load(f)


def _row(idx: int) -> dict:
    return SAMPLE_ROWS[idx]


# ── Account tools ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_token_valid():
    from models.inputs import CheckTokenInput
    from tools.account_tools import check_token

    with patch("tools.account_tools.meta_client") as mock_client:
        mock_client.get = AsyncMock(return_value={"id": "u123", "name": "Shashank"})
        result = await check_token(CheckTokenInput())

    assert result.valid is True
    assert result.user_id == "u123"
    assert result.user_name == "Shashank"


@pytest.mark.asyncio
async def test_check_token_error():
    from models.inputs import CheckTokenInput
    from tools.account_tools import check_token

    with patch("tools.account_tools.meta_client") as mock_client:
        mock_client.get = AsyncMock(side_effect=Exception("OAuthException: Token expired"))
        result = await check_token(CheckTokenInput())

    assert result.valid is False
    assert "Token expired" in result.error


@pytest.mark.asyncio
async def test_list_ad_accounts():
    from models.inputs import ListAdAccountsInput
    from tools.account_tools import list_ad_accounts

    with patch("tools.account_tools.meta_client") as mock_client:
        mock_client.paginate = AsyncMock(return_value=[
            {"id": "act_123", "account_id": "123", "name": "Test Acct",
             "currency": "INR", "account_status": 1},
        ])
        result = await list_ad_accounts(ListAdAccountsInput())

    assert result.count == 1
    assert result.accounts[0].account_status == "ACTIVE"


# ── Data tools ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_dashboard_snapshot():
    from models.inputs import GetDashboardSnapshotInput
    from tools.data_tools import get_dashboard_snapshot

    with patch("tools.data_tools.fetch_dashboard", new_callable=AsyncMock) as mock_fd:
        mock_fd.return_value = SAMPLE_ROWS
        result = await get_dashboard_snapshot(GetDashboardSnapshotInput())

    assert result.count == len(SAMPLE_ROWS)
    assert result.rows[0].id == SAMPLE_ROWS[0]["id"]


@pytest.mark.asyncio
async def test_get_insights():
    from models.inputs import GetInsightsInput
    from tools.data_tools import get_insights

    row = _row(0)
    fake_window = {
        "today":      row["today"],
        "yesterday":  row["yesterday"],
        "day_before": row["day_before"],
    }
    with patch("tools.data_tools.fetch_insights_for_object", new_callable=AsyncMock) as mock_fi:
        mock_fi.return_value = fake_window
        result = await get_insights(GetInsightsInput(object_id=row["id"], level="adset"))

    assert result.object_id == row["id"]
    assert result.today.cac == row["today"]["cac"]


# ── Optimiser tools ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_optimiser_dry_run():
    from models.inputs import RunOptimiserInput
    from tools.optimiser_tools import run_optimiser

    with patch("tools.optimiser_tools.fetch_dashboard", new_callable=AsyncMock) as mock_fd:
        mock_fd.return_value = SAMPLE_ROWS
        result = await run_optimiser(RunOptimiserInput(dry_run=True))

    assert result.dry_run is True
    assert isinstance(result.recommendations, list)
    # All 3 rows are D2/D3+ with data — should all produce recommendations
    assert result.count == len(SAMPLE_ROWS)


@pytest.mark.asyncio
async def test_explain_decision_uses_provided_metrics():
    from models.inputs import ExplainDecisionInput
    from tools.optimiser_tools import explain_decision

    inp = ExplainDecisionInput(
        object_id="23851234567890",
        level="adset",
        age_days=2,
        budget=2000,
        t_spend=1200.0, t_results=10.0, t_cac=120, t_cpi=100,
        y_cac=122, y_results=9.0, dby_cac=125,
    )
    # Should not call fetch_dashboard since metrics provided
    with patch("tools.optimiser_tools.fetch_dashboard", new_callable=AsyncMock) as mock_fd:
        result = await explain_decision(inp)
        mock_fd.assert_not_called()

    assert result.object_id == "23851234567890"
    assert isinstance(result.steps, list)
    assert len(result.steps) > 0


@pytest.mark.asyncio
async def test_simulate_budget_change():
    from models.inputs import SimulateBudgetChangeInput
    from tools.optimiser_tools import simulate_budget_change

    inp = SimulateBudgetChangeInput(
        level="adset", budget=2000, age_days=2,
        t_spend=1200.0, t_results=10.0, t_cac=120, t_cpi=100,
        y_cac=122, y_results=9.0, dby_cac=125,
    )
    result = await simulate_budget_change(inp)
    assert result.action in ("SET_BUDGET", "PAUSE", "")
    assert isinstance(result.steps, list)


# ── Write tools ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_budget_change_dry_run():
    from models.inputs import ApplyBudgetChangeInput
    from tools.write_tools import apply_budget_change

    with patch("tools.write_tools.meta_client") as mock_client:
        result = await apply_budget_change(ApplyBudgetChangeInput(
            object_id="23851234567890", level="adset", new_budget=3000, dry_run=True,
        ))
        mock_client.write.assert_not_called()

    assert result.dry_run is True
    assert result.success is True
    assert result.action_taken == "would_set_budget"


@pytest.mark.asyncio
async def test_apply_budget_change_below_floor():
    from models.inputs import ApplyBudgetChangeInput
    from tools.write_tools import apply_budget_change

    result = await apply_budget_change(ApplyBudgetChangeInput(
        object_id="23851234567890", level="adset", new_budget=500, dry_run=False,
    ))
    assert result.success is False
    assert "below floor" in (result.error or "")


@pytest.mark.asyncio
async def test_apply_budget_change_live():
    from models.inputs import ApplyBudgetChangeInput
    from tools.write_tools import apply_budget_change

    with patch("tools.write_tools.meta_client") as mock_client, \
         patch("tools.write_tools.log_action"):
        mock_client.get = AsyncMock(return_value={"daily_budget": "200000", "name": "Test"})
        mock_client.write = AsyncMock(return_value={"success": True})
        result = await apply_budget_change(ApplyBudgetChangeInput(
            object_id="23851234567890", level="adset", new_budget=3000, dry_run=False,
        ))

    assert result.success is True
    assert result.new_budget == 3000
    # Verify write was called with minor units
    call_fields = mock_client.write.call_args.args[1]
    assert call_fields["daily_budget"] == "300000"


@pytest.mark.asyncio
async def test_pause_object_dry_run():
    from models.inputs import PauseObjectInput
    from tools.write_tools import pause_object

    with patch("tools.write_tools.meta_client") as mock_client:
        result = await pause_object(PauseObjectInput(
            object_id="23851234567890", level="adset", dry_run=True,
        ))
        mock_client.write.assert_not_called()

    assert result.dry_run is True
    assert result.action_taken == "would_pause"


@pytest.mark.asyncio
async def test_pause_object_live():
    from models.inputs import PauseObjectInput
    from tools.write_tools import pause_object

    with patch("tools.write_tools.meta_client") as mock_client, \
         patch("tools.write_tools.log_action"):
        mock_client.get = AsyncMock(return_value={"name": "Test AdSet"})
        mock_client.write = AsyncMock(return_value={"success": True})
        result = await pause_object(PauseObjectInput(
            object_id="23851234567890", level="adset", dry_run=False,
        ))

    assert result.success is True
    mock_client.write.assert_called_once_with("23851234567890", {"status": "PAUSED"})


@pytest.mark.asyncio
async def test_bulk_apply_changes_dry_run():
    from models.inputs import BulkApplyChangesInput, BulkChange
    from tools.write_tools import bulk_apply_changes

    with patch("tools.write_tools.meta_client"):
        result = await bulk_apply_changes(BulkApplyChangesInput(
            changes=[
                BulkChange(object_id="111", level="adset", action="SET_BUDGET", new_budget=2000),
                BulkChange(object_id="222", level="adset", action="PAUSE"),
            ],
            dry_run=True,
        ))

    assert result.dry_run is True
    assert result.success_count == 2
    assert result.error_count == 0


@pytest.mark.asyncio
async def test_bulk_apply_unknown_action():
    from models.inputs import BulkApplyChangesInput, BulkChange
    from tools.write_tools import bulk_apply_changes

    result = await bulk_apply_changes(BulkApplyChangesInput(
        changes=[BulkChange(object_id="111", level="adset", action="DELETE")],
        dry_run=True,
    ))
    assert result.error_count == 1
    assert "Unknown action" in (result.results[0].error or "")


# ── Report tools ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_alerts_high_cac():
    from models.inputs import GetAlertsInput
    from tools.report_tools import get_alerts

    with patch("tools.report_tools.fetch_dashboard", new_callable=AsyncMock) as mock_fd:
        mock_fd.return_value = SAMPLE_ROWS  # row[2] has cac=250 (== threshold, not >), row[1] has cac=191
        result = await get_alerts(GetAlertsInput())

    # ALERT_CAC_THRESHOLD=300, ALERT_BUDGET_THRESHOLD=3000
    # row[0]: cac=120 (ok), budget=2000 (ok) — no alert
    # row[1]: cac=191 (ok), budget=5000 (>3000) — HIGH_BUDGET
    # row[2]: cac=250 (<300 ok), budget=8000 (>3000) — HIGH_BUDGET
    high_budget_alerts = [a for a in result.alerts if a.alert_type == "HIGH_BUDGET"]
    assert len(high_budget_alerts) >= 2


@pytest.mark.asyncio
async def test_get_alerts_both_thresholds():
    from models.inputs import GetAlertsInput
    from tools.report_tools import get_alerts

    high_row = {**SAMPLE_ROWS[0], "today": {**SAMPLE_ROWS[0]["today"], "cac": 350}, "budget": 5000}
    with patch("tools.report_tools.fetch_dashboard", new_callable=AsyncMock) as mock_fd:
        mock_fd.return_value = [high_row]
        result = await get_alerts(GetAlertsInput())

    assert result.count == 1
    assert result.alerts[0].alert_type == "HIGH_CAC_AND_BUDGET"


@pytest.mark.asyncio
async def test_get_report_snapshot_writes_cache():
    from models.inputs import GetReportSnapshotInput
    from tools.report_tools import get_report_snapshot

    summary_data = {
        "accounts": [{
            "account": "TestAccount", "spend_today": 1200.0, "spend_yesterday": 1100.0,
            "spend_day_before": 1000.0, "results_today": 10.0, "results_yesterday": 9.0,
            "total_daily_budget": 2000, "est_spend_after_change": 2000,
            "scale_count": 0, "cut_count": 0, "pause_count": 0, "blended_cac": 120,
        }],
        "drift_items": [],
        "new_cache": {"23851234567890": {"cac": 120, "spend": 1200, "cpi": 100}},
        "overall_spend": 1200.0, "overall_results": 10.0,
        "overall_cac": 120, "overall_budget": 2000,
    }

    with patch("tools.report_tools.summarize_accounts", new_callable=AsyncMock) as mock_sa, \
         patch("tools.report_tools.write_cache") as mock_wc:
        mock_sa.return_value = summary_data
        result = await get_report_snapshot(GetReportSnapshotInput())
        mock_wc.assert_called_once_with(summary_data["new_cache"])

    assert len(result.accounts) == 1
    assert result.accounts[0].blended_cac == 120
    assert result.overall_cac == 120


@pytest.mark.asyncio
async def test_get_drift_analysis():
    from models.inputs import GetDriftAnalysisInput
    from tools.report_tools import get_drift_analysis

    summary_data = {
        "accounts": [], "new_cache": {},
        "overall_spend": 0, "overall_results": 0, "overall_cac": None, "overall_budget": 0,
        "drift_items": [{
            "object_id": "23851234567890", "name": "Test", "account": "TestAccount",
            "level": "adset", "drift": "IMPROVED", "prev_cac": 130, "current_cac": 120,
            "delta_pct": -7.7,
        }],
    }

    with patch("tools.report_tools.summarize_accounts", new_callable=AsyncMock) as mock_sa:
        mock_sa.return_value = summary_data
        result = await get_drift_analysis(GetDriftAnalysisInput())

    assert result.count == 1
    assert result.items[0].drift == "IMPROVED"


@pytest.mark.asyncio
async def test_get_action_log():
    from models.inputs import GetActionLogInput
    from tools.report_tools import get_action_log

    fake_rows = [{
        "id": 1, "timestamp": "2026-05-07T10:00:00+05:30",
        "account": "TestAccount", "object_id": "23851234567890",
        "level": "adset", "name": "Test AdSet", "action": "SET_BUDGET",
        "old_budget": 2000, "new_budget": 3000,
        "cac_at_apply": None, "spend_at_apply": None,
        "result": "ok", "dry_run": 0,
    }]

    with patch("tools.report_tools.query_log", return_value=fake_rows):
        result = await get_action_log(GetActionLogInput(date="2026-05-07"))

    assert result.count == 1
    assert result.entries[0].dry_run is False
    assert result.entries[0].new_budget == 3000
