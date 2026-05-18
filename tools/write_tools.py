import datetime

import pytz
import structlog
from fastmcp import FastMCP

from core.meta_client import meta_client
from core.safety import validate_budget
from models.inputs import BulkChange
from models.outputs import (
    ApplyBudgetChangeOutput,
    BulkApplyChangesOutput,
    BulkChangeResult,
    PauseObjectOutput,
)
from persistence.action_log import log_action

write_tools = FastMCP("write-tools")
log = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")


def _ist_now() -> str:
    return datetime.datetime.now(IST).isoformat()


@write_tools.tool
async def apply_budget_change(
    object_id: str,
    level: str,
    new_budget: int,
    dry_run: bool = True,
) -> ApplyBudgetChangeOutput:
    """Apply a budget change to a campaign or ad set. dry_run=True by default — no API call made."""
    if dry_run:
        return ApplyBudgetChangeOutput(
            success=True,
            object_id=object_id,
            action_taken="would_set_budget",
            new_budget=new_budget,
            dry_run=True,
        )

    ok, err = validate_budget(new_budget)
    if not ok:
        return ApplyBudgetChangeOutput(
            success=False,
            object_id=object_id,
            action_taken="rejected",
            dry_run=False,
            error=err,
        )

    old_budget: int | None = None
    name = ""
    try:
        current = await meta_client.get(object_id, fields=["daily_budget", "name"])
        db_minor = int(current.get("daily_budget") or 0)
        old_budget = db_minor // 100
        name = current.get("name", "")
    except Exception as e:
        log.warning("write_prefetch_failed", object_id=object_id, error=str(e))

    result_str = "ok"
    success = True
    try:
        await meta_client.write(object_id, {"daily_budget": str(new_budget * 100)})
        log.info("budget_changed", object_id=object_id, new_budget=new_budget)
    except Exception as e:
        result_str = f"ERROR: {e}"
        success = False
        log.error("budget_change_failed", object_id=object_id, error=str(e))

    log_action(
        timestamp=_ist_now(),
        account=None,
        object_id=object_id,
        level=level,
        name=name,
        action="SET_BUDGET",
        old_budget=old_budget,
        new_budget=new_budget if success else None,
        cac_at_apply=None,
        spend_at_apply=None,
        result=result_str,
        dry_run=0,
    )

    return ApplyBudgetChangeOutput(
        success=success,
        object_id=object_id,
        action_taken="set_budget" if success else "failed",
        old_budget=old_budget,
        new_budget=new_budget if success else None,
        dry_run=False,
        error=None if success else result_str,
    )


@write_tools.tool
async def pause_object(
    object_id: str,
    level: str,
    dry_run: bool = True,
) -> PauseObjectOutput:
    """Pause a campaign or ad set. dry_run=True by default — no API call made."""
    if dry_run:
        return PauseObjectOutput(
            success=True,
            object_id=object_id,
            action_taken="would_pause",
            dry_run=True,
        )

    name = ""
    try:
        current = await meta_client.get(object_id, fields=["name"])
        name = current.get("name", "")
    except Exception as e:
        log.warning("write_prefetch_failed", object_id=object_id, error=str(e))

    result_str = "ok"
    success = True
    try:
        await meta_client.write(object_id, {"status": "PAUSED"})
        log.info("object_paused", object_id=object_id)
    except Exception as e:
        result_str = f"ERROR: {e}"
        success = False
        log.error("pause_failed", object_id=object_id, error=str(e))

    log_action(
        timestamp=_ist_now(),
        account=None,
        object_id=object_id,
        level=level,
        name=name,
        action="PAUSE",
        old_budget=None,
        new_budget=None,
        cac_at_apply=None,
        spend_at_apply=None,
        result=result_str,
        dry_run=0,
    )

    return PauseObjectOutput(
        success=success,
        object_id=object_id,
        action_taken="pause" if success else "failed",
        dry_run=False,
        error=None if success else result_str,
    )


@write_tools.tool
async def bulk_apply_changes(
    changes: list[BulkChange],
    dry_run: bool = True,
) -> BulkApplyChangesOutput:
    """Apply multiple budget changes and pauses in one call. dry_run=True by default."""
    results: list[BulkChangeResult] = []
    success_count = error_count = 0

    for change in changes:
        try:
            if change.action == "SET_BUDGET":
                r = await apply_budget_change(
                    object_id=change.object_id,
                    level=change.level,
                    new_budget=change.new_budget or 0,
                    dry_run=dry_run,
                )
                ok = r.success
                action_taken = r.action_taken
                err = r.error
            elif change.action == "PAUSE":
                r = await pause_object(
                    object_id=change.object_id,
                    level=change.level,
                    dry_run=dry_run,
                )
                ok = r.success
                action_taken = r.action_taken
                err = r.error
            else:
                ok = False
                action_taken = "unknown_action"
                err = f"Unknown action: {change.action}"

            results.append(
                BulkChangeResult(
                    object_id=change.object_id,
                    action_taken=action_taken,
                    success=ok,
                    error=err,
                )
            )
            if ok:
                success_count += 1
            else:
                error_count += 1

        except Exception as e:
            results.append(
                BulkChangeResult(
                    object_id=change.object_id,
                    action_taken="error",
                    success=False,
                    error=str(e),
                )
            )
            error_count += 1

    return BulkApplyChangesOutput(
        results=results,
        success_count=success_count,
        error_count=error_count,
        dry_run=dry_run,
    )
