from fastmcp import FastMCP
import structlog

from core.meta_client import meta_client
from core.safety import validate_budget
from models.inputs import (
    CreateCampaignInput,
    GetCampaignInput,
    ListCampaignsInput,
    UpdateCampaignInput,
    DeleteCampaignInput,
)
from models.outputs import (
    CampaignOutput,
    CreateCampaignOutput,
    GetCampaignOutput,
    ListCampaignsOutput,
    UpdateCampaignOutput,
    DeleteCampaignOutput,
)

campaign_tools = FastMCP("campaign-tools")
log = structlog.get_logger()


@campaign_tools.tool
async def create_campaign(input: CreateCampaignInput) -> CreateCampaignOutput:
    """Create a new Meta advertising campaign in the specified ad account."""
    account_id = input.account_id
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"

    data = {
        "name": input.name,
        "objective": input.objective,
        "status": input.status,
        "special_ad_categories": "[]",
        "is_adset_budget_sharing_enabled": "false",
    }

    if input.daily_budget:
        ok, err = validate_budget(input.daily_budget)
        if not ok:
            return CreateCampaignOutput(success=False, error=err)
        data["daily_budget"] = str(input.daily_budget * 100)

    try:
        result = await meta_client.post(f"{account_id}/campaigns", data)
        campaign_id = result.get("id")
        log.info("campaign_created", account_id=account_id, campaign_id=campaign_id, name=input.name)
        return CreateCampaignOutput(success=True, campaign_id=campaign_id)
    except Exception as e:
        log.error("campaign_creation_failed", account_id=account_id, error=str(e))
        return CreateCampaignOutput(success=False, error=str(e))


@campaign_tools.tool
async def get_campaign(input: GetCampaignInput) -> GetCampaignOutput:
    """Get details of a specific campaign by ID."""
    try:
        fields = ",".join(input.fields)
        result = await meta_client.get(input.campaign_id, fields=input.fields)
        
        campaign = CampaignOutput(
            id=result.get("id", ""),
            name=result.get("name", ""),
            status=result.get("status", ""),
            objective=result.get("objective", ""),
            daily_budget=int(result.get("daily_budget", 0)) // 100 if result.get("daily_budget") else None,
            created_time=result.get("created_time"),
        )
        return GetCampaignOutput(campaign=campaign)
    except Exception as e:
        log.error("get_campaign_failed", campaign_id=input.campaign_id, error=str(e))
        return GetCampaignOutput(error=str(e))


@campaign_tools.tool
async def list_campaigns(input: ListCampaignsInput) -> ListCampaignsOutput:
    """List all campaigns in an ad account with optional status filter."""
    account_id = input.account_id
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"

    params = {
        "fields": "id,name,status,objective,daily_budget,created_time",
        "limit": input.limit,
    }

    if input.status_filter:
        status_filter = f'[{{"field":"status","operator":"EQUAL","value":"{input.status_filter}"}}]'
        params["filtering"] = status_filter

    try:
        campaigns = await meta_client.paginate(f"{account_id}/campaigns", params)
        
        results = []
        for camp in campaigns:
            results.append(CampaignOutput(
                id=camp.get("id", ""),
                name=camp.get("name", ""),
                status=camp.get("status", ""),
                objective=camp.get("objective", ""),
                daily_budget=int(camp.get("daily_budget", 0)) // 100 if camp.get("daily_budget") else None,
                created_time=camp.get("created_time"),
            ))
        
        log.info("campaigns_listed", account_id=account_id, count=len(results))
        return ListCampaignsOutput(campaigns=results, count=len(results))
    except Exception as e:
        log.error("list_campaigns_failed", account_id=account_id, error=str(e))
        return ListCampaignsOutput(campaigns=[], count=0)


@campaign_tools.tool
async def update_campaign(input: UpdateCampaignInput) -> UpdateCampaignOutput:
    """Update campaign properties (name, status, budget)."""
    data = {}
    
    if input.name:
        data["name"] = input.name
    if input.status:
        data["status"] = input.status
    if input.daily_budget:
        ok, err = validate_budget(input.daily_budget)
        if not ok:
            return UpdateCampaignOutput(success=False, campaign_id=input.campaign_id, error=err)
        data["daily_budget"] = str(input.daily_budget * 100)

    if not data:
        return UpdateCampaignOutput(
            success=False, 
            campaign_id=input.campaign_id, 
            error="No valid fields to update"
        )

    try:
        await meta_client.write(input.campaign_id, data)
        log.info("campaign_updated", campaign_id=input.campaign_id)
        return UpdateCampaignOutput(success=True, campaign_id=input.campaign_id)
    except Exception as e:
        log.error("campaign_update_failed", campaign_id=input.campaign_id, error=str(e))
        return UpdateCampaignOutput(success=False, campaign_id=input.campaign_id, error=str(e))


@campaign_tools.tool
async def delete_campaign(input: DeleteCampaignInput) -> DeleteCampaignOutput:
    """Delete a campaign by setting its status to DELETED."""
    try:
        await meta_client.write(input.campaign_id, {"status": "DELETED"})
        log.info("campaign_deleted", campaign_id=input.campaign_id)
        return DeleteCampaignOutput(success=True, campaign_id=input.campaign_id)
    except Exception as e:
        log.error("campaign_delete_failed", campaign_id=input.campaign_id, error=str(e))
        return DeleteCampaignOutput(success=False, campaign_id=input.campaign_id, error=str(e))