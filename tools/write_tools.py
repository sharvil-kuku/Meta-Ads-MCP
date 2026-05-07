from fastmcp import FastMCP

from models.inputs import ApplyBudgetChangeInput, BulkApplyChangesInput, PauseObjectInput
from models.outputs import ApplyBudgetChangeOutput, BulkApplyChangesOutput, PauseObjectOutput

write_tools = FastMCP("write-tools")


@write_tools.tool
async def apply_budget_change(input: ApplyBudgetChangeInput) -> ApplyBudgetChangeOutput:
    """Apply a budget change to a campaign or ad set. dry_run=True by default — no API call made."""
    action = "would_set_budget" if input.dry_run else "set_budget"
    return ApplyBudgetChangeOutput(
        success=True,
        object_id=input.object_id,
        action_taken=action,
        new_budget=input.new_budget,
        dry_run=input.dry_run,
    )


@write_tools.tool
async def pause_object(input: PauseObjectInput) -> PauseObjectOutput:
    """Pause a campaign or ad set. dry_run=True by default — no API call made."""
    action = "would_pause" if input.dry_run else "pause"
    return PauseObjectOutput(
        success=True,
        object_id=input.object_id,
        action_taken=action,
        dry_run=input.dry_run,
    )


@write_tools.tool
async def bulk_apply_changes(input: BulkApplyChangesInput) -> BulkApplyChangesOutput:
    """Apply multiple budget changes and pauses in one call. dry_run=True by default."""
    from models.outputs import BulkChangeResult
    results = [
        BulkChangeResult(
            object_id=c.object_id,
            action_taken=f"would_{c.action.lower()}" if input.dry_run else c.action.lower(),
            success=True,
        )
        for c in input.changes
    ]
    return BulkApplyChangesOutput(
        results=results,
        success_count=len(results),
        error_count=0,
        dry_run=input.dry_run,
    )
