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
from models.outputs import (
    DecisionStep,
    ExplainDecisionOutput,
    OptimiserRecommendation,
    RunOptimiserOutput,
    SimulateBudgetChangeOutput,
)

optimiser_tools = FastMCP("optimiser-tools")


@optimiser_tools.tool
async def run_optimiser(
    account_ids: list[str] | None = None,
    dry_run: bool = True,
) -> RunOptimiserOutput:
    """Run budget optimiser across all active ad sets and campaigns. Returns recommendations."""
    rows = await fetch_dashboard(account_ids=account_ids)

    recommendations = []
    for row in rows:
        ctx = ctx_from_row(row)
        result = decide(ctx)

        recommendations.append(
            OptimiserRecommendation(
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
            )
        )

    return RunOptimiserOutput(
        recommendations=recommendations,
        count=len(recommendations),
        dry_run=dry_run,
    )


@optimiser_tools.tool
async def explain_decision(
    object_id: str,
    level: str = "adset",
    t_spend: float | None = None,
    t_results: float | None = None,
    t_cac: float | None = None,
    t_cpi: float | None = None,
    y_cac: float | None = None,
    y_results: float | None = None,
    dby_cac: float | None = None,
    budget: int | None = None,
    age_days: int | None = None,
    conversion: float = 0,
    has_conversion: bool = False,
) -> ExplainDecisionOutput:
    """Explain the optimiser decision for a single object with step-by-step trace."""

    if budget is not None and t_cac is not None:
        age = age_days if age_days is not None else 9999
        bgt = budget
        ctx = DecisionContext(
            level=level,
            structure=classify_structure(level, bgt),
            day_bucket=bucket_from_age(age),
            age_days=age,
            budget=bgt,
            t_spend=t_spend or 0,
            t_results=t_results or 0,
            t_cac=t_cac or 0,
            t_cpi=t_cpi or 0,
            y_cac=y_cac or 0,
            y_results=y_results or 0,
            dby_cac=dby_cac or 0,
            conversion=conversion,
            has_conversion=has_conversion,
        )
    else:
        window = await fetch_insights_for_object(object_id)
        row = {
            "id": object_id,
            "level": level,
            "budget": budget or 0,
            "start_time": None,
            "today": window["today"],
            "yesterday": window["yesterday"],
            "day_before": window["day_before"],
        }
        ctx = ctx_from_row(row)

    result = decide_with_trace(ctx)
    return ExplainDecisionOutput(
        object_id=object_id,
        action=result.action,
        new_budget=result.new_budget,
        reason=result.reason,
        steps=[DecisionStep(step=s["step"], value=s["value"]) for s in result.steps],
    )


@optimiser_tools.tool
async def simulate_budget_change(
    level: str,
    budget: int,
    t_spend: float,
    t_results: float,
    t_cac: float,
    t_cpi: float,
    y_cac: float,
    y_results: float,
    dby_cac: float,
    age_days: int,
    conversion: float = 0,
    has_conversion: bool = False,
) -> SimulateBudgetChangeOutput:
    """Simulate an optimiser decision from provided metrics. No API call."""
    ctx = DecisionContext(
        level=level,
        structure=classify_structure(level, budget),
        day_bucket=bucket_from_age(age_days),
        age_days=age_days,
        budget=budget,
        t_spend=t_spend,
        t_results=t_results,
        t_cac=t_cac,
        t_cpi=t_cpi,
        y_cac=y_cac,
        y_results=y_results,
        dby_cac=dby_cac,
        conversion=conversion,
        has_conversion=has_conversion,
    )
    result = decide_with_trace(ctx)
    return SimulateBudgetChangeOutput(
        action=result.action,
        new_budget=result.new_budget,
        reason=result.reason,
        steps=[DecisionStep(step=s["step"], value=s["value"]) for s in result.steps],
    )
