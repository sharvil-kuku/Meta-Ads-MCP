from fastmcp import FastMCP
import structlog

from core.meta_client import meta_client
from core.safety import validate_budget
from models.inputs import (
    CreateAdSetInput,
    GetAdSetInput,
    ListAdSetsInput,
    UpdateAdSetInput,
    DeleteAdSetInput,
)
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
async def create_adset(input: CreateAdSetInput) -> CreateAdSetOutput:
    """Create a new ad set within a campaign with targeting, budget, and bid settings."""
    data = {
        "name": input.name,
        "campaign_id": input.campaign_id,
        "daily_budget": str(input.daily_budget * 100),
        "billing_event": input.billing_event,
        "optimization_goal": input.optimization_goal,
        "status": input.status,
    }

    if input.bid_amount:
        data["bid_amount"] = str(input.bid_amount)

    if input.targeting:
        import json
        data["targeting"] = json.dumps(input.targeting)

    try:
        # Fetch campaign to get account_id
        campaign = await meta_client.get(input.campaign_id, fields=["account_id"])
        account_id = campaign.get("account_id")
        if not account_id:
            return CreateAdSetOutput(success=False, error=f"Could not find account_id for campaign {input.campaign_id}")
        
        if not account_id.startswith("act_"):
            account_id = f"act_{account_id}"

        result = await meta_client.post(f"{account_id}/adsets", data)
        adset_id = result.get("id")
        log.info("adset_created", campaign_id=input.campaign_id, adset_id=adset_id, name=input.name)
        return CreateAdSetOutput(success=True, adset_id=adset_id)
    except Exception as e:
        log.error("adset_creation_failed", campaign_id=input.campaign_id, error=str(e))
        return CreateAdSetOutput(success=False, error=str(e))


@adset_tools.tool
async def get_adset(input: GetAdSetInput) -> GetAdSetOutput:
    """Get details of a specific ad set by ID."""
    try:
        result = await meta_client.get(input.adset_id, fields=input.fields)
        
        adset = AdSetOutput(
            id=result.get("id", ""),
            name=result.get("name", ""),
            status=result.get("status", ""),
            campaign_id=result.get("campaign_id", ""),
            daily_budget=int(result.get("daily_budget", 0)) // 100 if result.get("daily_budget") else None,
            bid_amount=int(result.get("bid_amount", 0)) // 100 if result.get("bid_amount") else None,
            targeting=result.get("targeting"),
        )
        return GetAdSetOutput(adset=adset)
    except Exception as e:
        log.error("get_adset_failed", adset_id=input.adset_id, error=str(e))
        return GetAdSetOutput(error=str(e))


@adset_tools.tool
async def list_adsets(input: ListAdSetsInput) -> ListAdSetsOutput:
    """List all ad sets for a campaign with optional status filter."""
    params = {
        "fields": "id,name,status,campaign_id,daily_budget,bid_amount,targeting",
        "limit": input.limit,
    }

    if input.status_filter:
        status_filter = f'[{{"field":"status","operator":"EQUAL","value":"{input.status_filter}"}}]'
        params["filtering"] = status_filter

    try:
        adsets = await meta_client.paginate(f"{input.campaign_id}/adsets", params)
        
        results = []
        for adset in adsets:
            results.append(AdSetOutput(
                id=adset.get("id", ""),
                name=adset.get("name", ""),
                status=adset.get("status", ""),
                campaign_id=adset.get("campaign_id", ""),
                daily_budget=int(adset.get("daily_budget", 0)) // 100 if adset.get("daily_budget") else None,
                bid_amount=int(adset.get("bid_amount", 0)) // 100 if adset.get("bid_amount") else None,
                targeting=adset.get("targeting"),
            ))
        
        log.info("adsets_listed", campaign_id=input.campaign_id, count=len(results))
        return ListAdSetsOutput(adsets=results, count=len(results))
    except Exception as e:
        log.error("list_adsets_failed", campaign_id=input.campaign_id, error=str(e))
        return ListAdSetsOutput(adsets=[], count=0)


@adset_tools.tool
async def update_adset(input: UpdateAdSetInput) -> UpdateAdSetOutput:
    """Update ad set properties (name, status, budget, bid)."""
    data = {}
    
    if input.name:
        data["name"] = input.name
    if input.status:
        data["status"] = input.status
    if input.daily_budget:
        ok, err = validate_budget(input.daily_budget)
        if not ok:
            return UpdateAdSetOutput(success=False, adset_id=input.adset_id, error=err)
        data["daily_budget"] = str(input.daily_budget * 100)
    if input.bid_amount:
        data["bid_amount"] = str(input.bid_amount)

    if not data:
        return UpdateAdSetOutput(
            success=False, 
            adset_id=input.adset_id, 
            error="No valid fields to update"
        )

    try:
        await meta_client.write(input.adset_id, data)
        log.info("adset_updated", adset_id=input.adset_id)
        return UpdateAdSetOutput(success=True, adset_id=input.adset_id)
    except Exception as e:
        log.error("adset_update_failed", adset_id=input.adset_id, error=str(e))
        return UpdateAdSetOutput(success=False, adset_id=input.adset_id, error=str(e))


@adset_tools.tool
async def delete_adset(input: DeleteAdSetInput) -> DeleteAdSetOutput:
    """Delete an ad set by setting its status to DELETED."""
    try:
        await meta_client.write(input.adset_id, {"status": "DELETED"})
        log.info("adset_deleted", adset_id=input.adset_id)
        return DeleteAdSetOutput(success=True, adset_id=input.adset_id)
    except Exception as e:
        log.error("adset_delete_failed", adset_id=input.adset_id, error=str(e))
        return DeleteAdSetOutput(success=False, adset_id=input.adset_id, error=str(e))