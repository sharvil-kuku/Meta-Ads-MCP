from fastmcp import FastMCP
from pydantic import BaseModel

optimiser_tools = FastMCP("optimiser-tools")


class OptimiserRecommendation(BaseModel):
    object_id: str
    name: str
    level: str
    action: str
    current_budget: int
    new_budget: int = 0
    reason: str


class RunOptimiserOutput(BaseModel):
    recommendations: list[OptimiserRecommendation]
    count: int


@optimiser_tools.tool
async def run_optimiser() -> RunOptimiserOutput:
    """Run budget optimiser across all active ad sets and campaigns. Returns recommendations."""
    return RunOptimiserOutput(recommendations=[], count=0)
