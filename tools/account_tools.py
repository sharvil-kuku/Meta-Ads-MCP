from fastmcp import FastMCP

from constants import STATUS_MAP
from core.meta_client import meta_client
from models.outputs import AdAccountOutput, CheckTokenOutput, ListAdAccountsOutput

account_tools = FastMCP("account-tools")


@account_tools.tool
async def check_token() -> CheckTokenOutput:
    """Validate Meta access token. Returns user id, name, and valid flag."""
    try:
        resp = await meta_client.get("me", fields=["id", "name"])
        return CheckTokenOutput(
            valid=True,
            user_id=resp.get("id"),
            user_name=resp.get("name"),
        )
    except Exception as e:
        return CheckTokenOutput(valid=False, error=str(e))


@account_tools.tool
async def list_ad_accounts(limit: int = 200) -> ListAdAccountsOutput:
    """List all accessible Meta ad accounts with status and currency."""
    try:
        params = {
            "fields": "id,account_id,name,currency,account_status",
            "limit": limit,
        }
        accounts = await meta_client.paginate("me/adaccounts", params)

        results = []
        for acct in accounts:
            status_code = acct.get("account_status", 2)
            status = STATUS_MAP.get(status_code, "UNKNOWN")
            results.append(
                AdAccountOutput(
                    account_id=acct.get("account_id", ""),
                    name=acct.get("name", ""),
                    account_status=status,
                    currency=acct.get("currency", "INR"),
                    id=acct.get("id", ""),
                )
            )

        return ListAdAccountsOutput(accounts=results, count=len(results))

    except Exception:
        return ListAdAccountsOutput(accounts=[], count=0)
