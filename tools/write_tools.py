from fastmcp import FastMCP
from pydantic import BaseModel

write_tools = FastMCP("write-tools")


class ApplyBudgetChangeInput(BaseModel):
    object_id: str
    new_budget: int
    dry_run: bool = True


class ApplyBudgetChangeOutput(BaseModel):
    success: bool
    action_taken: str
    dry_run: bool


@write_tools.tool
async def apply_budget_change(input: ApplyBudgetChangeInput) -> ApplyBudgetChangeOutput:
    """Apply a budget change to a campaign or ad set. dry_run=True by default — no API call made."""
    action = "would_set_budget" if input.dry_run else "set_budget"
    return ApplyBudgetChangeOutput(success=True, action_taken=action, dry_run=input.dry_run)
