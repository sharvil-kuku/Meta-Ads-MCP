from fastmcp import FastMCP

from models.inputs import RunOptimiserInput
from models.outputs import RunOptimiserOutput

optimiser_tools = FastMCP("optimiser-tools")


@optimiser_tools.tool
async def run_optimiser(input: RunOptimiserInput) -> RunOptimiserOutput:
    """Run budget optimiser across all active ad sets and campaigns. Returns recommendations."""
    return RunOptimiserOutput(recommendations=[], count=0, dry_run=input.dry_run)
