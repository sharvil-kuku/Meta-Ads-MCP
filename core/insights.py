import asyncio
import datetime
from typing import Optional

import pytz
import structlog

from config import settings
from core.meta_client import meta_client

log = structlog.get_logger()


# ── Pure helpers (exact ports from script.gs) ──────────────────────────────────

def pick_result(row: dict) -> float:
    """start_trial_mobile_app from conversions; fallback purchase from actions."""
    for a in (row.get("conversions") or []):
        if a.get("action_type") == "start_trial_mobile_app":
            return float(a.get("value", 0))
    for a in (row.get("actions") or []):
        if a.get("action_type") == "purchase":
            return float(a.get("value", 0))
    return 0.0


def count_install(row: dict) -> float:
    """mobile_app_install from conversions; fallback from actions."""
    for a in (row.get("conversions") or []):
        if a.get("action_type") == "mobile_app_install":
            return float(a.get("value", 0))
    for a in (row.get("actions") or []):
        if a.get("action_type") == "mobile_app_install":
            return float(a.get("value", 0))
    return 0.0


def empty_insights() -> dict:
    return {
        "today":      {"spend": 0.0, "installs": 0.0, "results": 0.0},
        "yesterday":  {"spend": 0.0, "installs": 0.0, "results": 0.0},
        "day_before": {"spend": 0.0, "installs": 0.0, "results": 0.0},
    }


def detect_campaign_type(campaign_name: str) -> str:
    return "App" if "app" in campaign_name.lower() else "Web"


def passes_owner_filter(campaign_name: str) -> bool:
    if not settings.owner_filter_enabled:
        return True
    return settings.owner_filter.lower() in (campaign_name or "").lower()


def _date_strings(tz_str: str) -> tuple[str, str, str, str, str]:
    """Return (since, until, today_str, yesterday_str, day_before_str) in account tz."""
    tz = pytz.timezone(tz_str)
    today = datetime.datetime.now(tz).date()
    yesterday = today - datetime.timedelta(days=1)
    day_before = today - datetime.timedelta(days=2)
    fmt = "%Y-%m-%d"
    return (
        day_before.strftime(fmt),   # since
        today.strftime(fmt),        # until
        today.strftime(fmt),        # today_str
        yesterday.strftime(fmt),    # y_str
        day_before.strftime(fmt),   # dby_str
    )


# ── API fetch functions ────────────────────────────────────────────────────────

async def fetch_campaigns(account_id: str) -> list[dict]:
    """Fetch ACTIVE+PAUSED campaigns for one account. account_id must be act_XXX format."""
    status_filter = (
        '[{"field":"effective_status","operator":"IN",'
        '"value":["ACTIVE","PAUSED","CAMPAIGN_PAUSED","ADSET_PAUSED"]}]'
    )
    params = {
        "fields": "id,name,status,effective_status,daily_budget,lifetime_budget,start_time",
        "filtering": status_filter,
        "limit": 200,
    }
    return await meta_client.paginate(f"{account_id}/campaigns", params)


async def fetch_adsets_for_campaigns(campaign_ids: list[str]) -> list[dict]:
    """Batch fetch ACTIVE adsets for given campaign IDs."""
    if not campaign_ids:
        return []

    status_filter = '[{"field":"effective_status","operator":"IN","value":["ACTIVE"]}]'
    fields = "id,name,status,effective_status,daily_budget,campaign_id,start_time"

    batch = [
        {
            "method": "GET",
            "relative_url": (
                f"{cid}/adsets?fields={fields}"
                f"&filtering={status_filter}&limit=200"
            ),
        }
        for cid in campaign_ids
    ]

    results = await meta_client.post_batch(batch)

    adsets: list[dict] = []
    for item in results:
        if item.get("code") == 200:
            body = item.get("body", {})
            if isinstance(body, dict):
                adsets.extend(body.get("data", []))
    return adsets


async def fetch_insights_windowed(
    object_ids: list[str],
    tz_str: str = "Asia/Kolkata",
) -> dict[str, dict]:
    """Batch fetch 3-day windowed insights. Returns {object_id: window_dict}."""
    if not object_ids:
        return {}

    since, until, today_str, y_str, dby_str = _date_strings(tz_str)
    fields = "spend,conversions,actions,date_start"
    time_range = f'{{"since":"{since}","until":"{until}"}}'

    batch = [
        {
            "method": "GET",
            "relative_url": (
                f"{oid}/insights?fields={fields}"
                f"&time_range={time_range}"
                f"&time_increment=1"
                f"&use_account_attribution_setting=true"
                f"&limit=10"
            ),
        }
        for oid in object_ids
    ]

    results = await meta_client.post_batch(batch)

    insights_map: dict[str, dict] = {}
    for oid, item in zip(object_ids, results):
        window = empty_insights()
        if item.get("code") == 200:
            body = item.get("body", {})
            if isinstance(body, dict):
                for day_row in body.get("data", []):
                    ds = day_row.get("date_start", "")
                    spend = float(day_row.get("spend", 0) or 0)
                    r_val = pick_result(day_row)
                    i_val = count_install(day_row)
                    slot = {"spend": spend, "results": r_val, "installs": i_val}
                    if ds == today_str:
                        window["today"] = slot
                    elif ds == y_str:
                        window["yesterday"] = slot
                    elif ds == dby_str:
                        window["day_before"] = slot
        insights_map[oid] = window

    return insights_map


# ── Row builder ────────────────────────────────────────────────────────────────

def build_row(
    obj_id: str,
    obj_name: str,
    account_name: str,
    account_id: str,
    level: str,
    status: str,
    budget: int,
    start_time: Optional[str],
    campaign_type: str,
    insights: dict,
) -> dict:
    t   = insights.get("today",      {})
    y   = insights.get("yesterday",  {})
    dby = insights.get("day_before", {})

    t_spend    = float(t.get("spend",    0))
    t_results  = float(t.get("results",  0))
    t_installs = float(t.get("installs", 0))
    y_spend    = float(y.get("spend",    0))
    y_results  = float(y.get("results",  0))
    dby_spend  = float(dby.get("spend",   0))
    dby_results= float(dby.get("results", 0))

    t_cac  = round(t_spend / t_results)    if t_results    else None
    t_cpi  = round(t_spend / t_installs)   if t_installs   else None
    y_cac  = round(y_spend / y_results)    if y_results    else None
    dby_cac= round(dby_spend / dby_results)if dby_results  else None

    return {
        "id":           obj_id,
        "name":         obj_name,
        "account":      account_name,
        "account_id":   account_id,
        "level":        level,
        "status":       status,
        "budget":       budget,
        "type":         campaign_type,
        "start_time":   start_time,
        "today": {
            "spend": t_spend, "results": t_results,
            "installs": t_installs, "cac": t_cac, "cpi": t_cpi,
        },
        "yesterday": {
            "spend": y_spend, "results": y_results,
            "installs": float(y.get("installs", 0)), "cac": y_cac, "cpi": None,
        },
        "day_before": {
            "spend": dby_spend, "results": dby_results,
            "installs": float(dby.get("installs", 0)), "cac": dby_cac, "cpi": None,
        },
    }


# ── Orchestrators ──────────────────────────────────────────────────────────────

async def fetch_dashboard(
    account_ids: list[str] | None = None,
    tz_str: str = "Asia/Kolkata",
) -> list[dict]:
    """Full dashboard: accounts → campaigns → adsets → insights → rows."""

    # Resolve accounts
    if not account_ids:
        raw = await meta_client.paginate(
            "me/adaccounts",
            {"fields": "id,account_id,name,currency,account_status", "limit": 200},
        )
        account_list = [
            {"id": a["id"], "name": a.get("name", a["id"])}
            for a in raw
            if a.get("account_status") == 1
        ]
    else:
        account_list = [
            {"id": aid if aid.startswith("act_") else f"act_{aid}", "name": aid}
            for aid in account_ids
        ]

    if not account_list:
        return []

    rows: list[dict] = []

    for account in account_list:
        acct_id   = account["id"]     # act_XXX
        acct_name = account["name"]

        campaigns_raw  = await fetch_campaigns(acct_id)
        active_campaigns = [c for c in campaigns_raw if c.get("effective_status") == "ACTIVE"]
        if not active_campaigns:
            continue

        campaign_ids = [c["id"] for c in active_campaigns]
        adsets_raw   = await fetch_adsets_for_campaigns(campaign_ids)

        all_object_ids: list[str] = []
        campaign_meta: dict[str, dict] = {}
        adset_meta:    dict[str, dict] = {}

        # CBO campaigns
        for c in active_campaigns:
            db_minor = int(c.get("daily_budget")    or 0)
            lb_minor = int(c.get("lifetime_budget") or 0)
            is_cbo   = db_minor > 0 or lb_minor > 0
            if not is_cbo:
                continue
            budget = (db_minor / 100) if db_minor else (lb_minor / 100)
            campaign_meta[c["id"]] = {
                "name":       c["name"],
                "budget":     int(budget),
                "start_time": c.get("start_time"),
                "type":       detect_campaign_type(c["name"]),
                "status":     c.get("effective_status", ""),
            }
            all_object_ids.append(c["id"])

        # ABO / AAA adsets
        for a in adsets_raw:
            db_minor = int(a.get("daily_budget") or 0)
            budget   = db_minor / 100
            adset_meta[a["id"]] = {
                "name":        a["name"],
                "budget":      int(budget),
                "campaign_id": a.get("campaign_id", ""),
                "start_time":  a.get("start_time"),
                "status":      a.get("effective_status", ""),
            }
            all_object_ids.append(a["id"])

        if not all_object_ids:
            continue

        insights_map = await fetch_insights_windowed(all_object_ids, tz_str)

        # Build CBO campaign rows
        for cid, cdata in campaign_meta.items():
            if not passes_owner_filter(cdata["name"]):
                continue
            rows.append(build_row(
                obj_id=cid,
                obj_name=cdata["name"],
                account_name=acct_name,
                account_id=acct_id,
                level="campaign",
                status=cdata["status"],
                budget=cdata["budget"],
                start_time=cdata["start_time"],
                campaign_type=cdata["type"],
                insights=insights_map.get(cid, empty_insights()),
            ))

        # Build adset rows — owner filter on parent campaign name
        campaign_name_by_id: dict[str, str] = {c["id"]: c["name"] for c in active_campaigns}
        for aid, adata in adset_meta.items():
            parent_name = campaign_name_by_id.get(adata["campaign_id"], "")
            if not passes_owner_filter(parent_name):
                continue
            rows.append(build_row(
                obj_id=aid,
                obj_name=adata["name"],
                account_name=acct_name,
                account_id=acct_id,
                level="adset",
                status=adata["status"],
                budget=adata["budget"],
                start_time=adata["start_time"],
                campaign_type=detect_campaign_type(parent_name),
                insights=insights_map.get(aid, empty_insights()),
            ))

    return rows


async def fetch_insights_for_object(
    object_id: str,
    tz_str: str = "Asia/Kolkata",
) -> dict:
    """Fetch 3-day insight window for a single campaign or ad set."""
    m = await fetch_insights_windowed([object_id], tz_str)
    return m.get(object_id, empty_insights())
