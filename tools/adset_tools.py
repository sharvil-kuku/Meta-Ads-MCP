from fastmcp import FastMCP
import structlog

from core.meta_client import meta_client
from core.safety import validate_budget
from models.outputs import (
    AdSetOutput,
    CreateAdSetOutput,
    GetAdSetOutput,
    ListAdSetsOutput,
    UpdateAdSetOutput,
    DeleteAdSetOutput,
)

adset_tools = FastMCP("adset-tools")
log = structlog.get_logger()


@adset_tools.tool
async def create_adset(
    campaign_id: str,
    name: str,
    daily_budget: int | None = None,
    billing_event: str = "IMPRESSIONS",
    optimization_goal: str | None = None,
    bid_amount: int | None = None,
    status: str = "PAUSED",
    targeting: dict | None = None,
) -> CreateAdSetOutput:
    """Create a new ad set within a campaign with targeting, budget, and bid settings."""
    try:
        campaign = await meta_client.get(
            campaign_id,
            fields=["account_id", "bid_strategy", "daily_budget", "lifetime_budget"],
        )
        account_id = campaign.get("account_id")
        if not account_id:
            return CreateAdSetOutput(
                success=False, error=f"Could not find account_id for campaign {campaign_id}"
            )

        is_cbo = bool(campaign.get("daily_budget") or campaign.get("lifetime_budget"))

        if not account_id.startswith("act_"):
            account_id = f"act_{account_id}"
    except Exception as e:
        log.error("fetch_campaign_failed", campaign_id=campaign_id, error=str(e))
        return CreateAdSetOutput(success=False, error=f"Failed to fetch campaign info: {str(e)}")

    data = {
        "name": name,
        "campaign_id": campaign_id,
        "status": status,
    }

    if daily_budget and not is_cbo:
        data["daily_budget"] = str(daily_budget * 100)
    elif daily_budget and is_cbo:
        log.warning(
            "budget_ignored_cbo",
            campaign_id=campaign_id,
            message="Budget provided but campaign is CBO. Ignoring adset budget.",
        )

    if billing_event:
        data["billing_event"] = billing_event
    if optimization_goal:
        data["optimization_goal"] = optimization_goal
    if bid_amount:
        data["bid_amount"] = str(bid_amount)

    effective_targeting = targeting or {"geo_locations": {"countries": ["IN"]}}
    import json
    data["targeting"] = json.dumps(effective_targeting)

    try:
        result = await meta_client.post(f"{account_id}/adsets", data)
        adset_id = result.get("id")
        log.info("adset_created", campaign_id=campaign_id, adset_id=adset_id, name=name)
        return CreateAdSetOutput(success=True, adset_id=adset_id)
    except Exception as e:
        log.error("adset_creation_failed", campaign_id=campaign_id, error=str(e))
        return CreateAdSetOutput(success=False, error=str(e))


@adset_tools.tool
async def get_adset(
    adset_id: str,
    fields: list[str] | None = None,
) -> GetAdSetOutput:
    """Get details of a specific ad set by ID."""
    if fields is None:
        fields = ["id", "name", "status", "daily_budget", "campaign_id", "targeting"]
    try:
        result = await meta_client.get(adset_id, fields=fields)

        adset = AdSetOutput(
            id=result.get("id", ""),
            name=result.get("name", ""),
            status=result.get("status", ""),
            campaign_id=result.get("campaign_id", ""),
            daily_budget=int(result.get("daily_budget", 0)) // 100
            if result.get("daily_budget")
            else None,
            bid_amount=int(result.get("bid_amount", 0)) // 100
            if result.get("bid_amount")
            else None,
            targeting=result.get("targeting"),
        )
        return GetAdSetOutput(adset=adset)
    except Exception as e:
        log.error("get_adset_failed", adset_id=adset_id, error=str(e))
        return GetAdSetOutput(error=str(e))


@adset_tools.tool
async def list_adsets(
    campaign_id: str,
    status_filter: str | None = None,
    limit: int = 100,
) -> ListAdSetsOutput:
    """List all ad sets for a campaign with optional status filter."""
    params = {
        "fields": "id,name,status,campaign_id,daily_budget,bid_amount,targeting",
        "limit": limit,
    }

    if status_filter:
        params["filtering"] = f'[{{"field":"status","operator":"EQUAL","value":"{status_filter}"}}]'

    try:
        adsets = await meta_client.paginate(f"{campaign_id}/adsets", params)

        results = []
        for adset in adsets:
            results.append(
                AdSetOutput(
                    id=adset.get("id", ""),
                    name=adset.get("name", ""),
                    status=adset.get("status", ""),
                    campaign_id=adset.get("campaign_id", ""),
                    daily_budget=int(adset.get("daily_budget", 0)) // 100
                    if adset.get("daily_budget")
                    else None,
                    bid_amount=int(adset.get("bid_amount", 0)) // 100
                    if adset.get("bid_amount")
                    else None,
                    targeting=adset.get("targeting"),
                )
            )

        log.info("adsets_listed", campaign_id=campaign_id, count=len(results))
        return ListAdSetsOutput(adsets=results, count=len(results))
    except Exception as e:
        log.error("list_adsets_failed", campaign_id=campaign_id, error=str(e))
        return ListAdSetsOutput(adsets=[], count=0)


@adset_tools.tool
async def update_adset(
    adset_id: str,
    name: str | None = None,
    status: str | None = None,
    daily_budget: int | None = None,
    bid_amount: int | None = None,
) -> UpdateAdSetOutput:
    """Update ad set properties (name, status, budget, bid)."""
    data = {}

    if name:
        data["name"] = name
    if status:
        data["status"] = status
    if daily_budget:
        ok, err = validate_budget(daily_budget)
        if not ok:
            return UpdateAdSetOutput(success=False, adset_id=adset_id, error=err)
        data["daily_budget"] = str(daily_budget * 100)
    if bid_amount:
        data["bid_amount"] = str(bid_amount)

    if not data:
        return UpdateAdSetOutput(
            success=False, adset_id=adset_id, error="No valid fields to update"
        )

    try:
        await meta_client.write(adset_id, data)
        log.info("adset_updated", adset_id=adset_id)
        return UpdateAdSetOutput(success=True, adset_id=adset_id)
    except Exception as e:
        log.error("adset_update_failed", adset_id=adset_id, error=str(e))
        return UpdateAdSetOutput(success=False, adset_id=adset_id, error=str(e))


@adset_tools.tool
async def delete_adset(adset_id: str) -> DeleteAdSetOutput:
    """Delete an ad set by setting its status to DELETED."""
    try:
        await meta_client.write(adset_id, {"status": "DELETED"})
        log.info("adset_deleted", adset_id=adset_id)
        return DeleteAdSetOutput(success=True, adset_id=adset_id)
    except Exception as e:
        log.error("adset_delete_failed", adset_id=adset_id, error=str(e))
        return DeleteAdSetOutput(success=False, adset_id=adset_id, error=str(e))
