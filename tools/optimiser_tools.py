from fastmcp import FastMCP

from core.insights import fetch_dashboard, fetch_insights_for_object
from core.optimiser import (
    DecisionContext,
    bucket_from_age,
    classify_structure,
    ctx_from_row,
    decide,
    decide_with_trace,
)
from models.inputs import ExplainDecisionInput, RunOptimiserInput, SimulateBudgetChangeInput
from models.outputs import (
    DecisionStep,
    ExplainDecisionOutput,
    OptimiserRecommendation,
    RunOptimiserOutput,
    SimulateBudgetChangeOutput,
)

optimiser_tools = FastMCP("optimiser-tools")


@optimiser_tools.tool
async def run_optimiser(input: RunOptimiserInput) -> RunOptimiserOutput:
    """Run budget optimiser across all active ad sets and campaigns. Returns recommendations."""
    rows = await fetch_dashboard(account_ids=input.account_ids)

    recommendations = []
    for row in rows:
        ctx    = ctx_from_row(row)
        result = decide(ctx)

        recommendations.append(OptimiserRecommendation(
            object_id=row["id"],
            name=row["name"],
            account=row["account"],
            level=row["level"],
            structure=ctx.structure,
            day_bucket=ctx.day_bucket,
            action=result.action,
            current_budget=ctx.budget,
            new_budget=result.new_budget,
            reason=result.reason,
            today_cac=row["today"].get("cac"),
            today_spend=float(row["today"].get("spend", 0)),
        ))

    return RunOptimiserOutput(
        recommendations=recommendations,
        count=len(recommendations),
        dry_run=input.dry_run,
    )


@optimiser_tools.tool
async def explain_decision(input: ExplainDecisionInput) -> ExplainDecisionOutput:
    """Explain the optimiser decision for a single object with step-by-step trace."""

    # Use provided metrics if available; else fetch live
    if input.budget is not None and input.t_cac is not None:
        age = input.age_days if input.age_days is not None else 9999
        bgt   = input.budget
        ctx   = DecisionContext(
            level=input.level,
            structure=classify_structure(input.level, bgt),
            day_bucket=bucket_from_age(age),
            age_days=age,
            budget=bgt,
            t_spend=input.t_spend or 0,
            t_results=input.t_results or 0,
            t_cac=input.t_cac or 0,
            t_cpi=input.t_cpi or 0,
            y_cac=input.y_cac or 0,
            y_results=input.y_results or 0,
            dby_cac=input.dby_cac or 0,
            conversion=input.conversion,
            has_conversion=input.has_conversion,
        )
    else:
        window = await fetch_insights_for_object(input.object_id)
        # Build minimal row for ctx_from_row
        row = {
            "id": input.object_id,
            "level": input.level,
            "budget": input.budget or 0,
            "start_time": None,
            "today":      window["today"],
            "yesterday":  window["yesterday"],
            "day_before": window["day_before"],
        }
        ctx = ctx_from_row(row)

    result = decide_with_trace(ctx)
    return ExplainDecisionOutput(
        object_id=input.object_id,
        action=result.action,
        new_budget=result.new_budget,
        reason=result.reason,
        steps=[DecisionStep(step=s["step"], value=s["value"]) for s in result.steps],
    )


@optimiser_tools.tool
async def simulate_budget_change(input: SimulateBudgetChangeInput) -> SimulateBudgetChangeOutput:
    """Simulate an optimiser decision from provided metrics. No API call."""
    ctx = DecisionContext(
        level=input.level,
        structure=classify_structure(input.level, input.budget),
        day_bucket=bucket_from_age(input.age_days),
        age_days=input.age_days,
        budget=input.budget,
        t_spend=input.t_spend,
        t_results=input.t_results,
        t_cac=input.t_cac,
        t_cpi=input.t_cpi,
        y_cac=input.y_cac,
        y_results=input.y_results,
        dby_cac=input.dby_cac,
        conversion=input.conversion,
        has_conversion=input.has_conversion,
    )
    result = decide_with_trace(ctx)
    return SimulateBudgetChangeOutput(
        action=result.action,
        new_budget=result.new_budget,
        reason=result.reason,
        steps=[DecisionStep(step=s["step"], value=s["value"]) for s in result.steps],
    )
