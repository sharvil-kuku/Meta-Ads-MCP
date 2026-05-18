"""Port of summarizeAccount_ from script.gs."""

import datetime
from typing import Any, Optional

import pytz
import structlog

from core.insights import fetch_dashboard
from persistence.action_log import query_log
from persistence.report_cache import read_cache

log = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")


# ── Internal helpers ───────────────────────────────────────────────────────────


def _today_ist() -> str:
    return datetime.datetime.now(IST).strftime("%Y-%m-%d")


def _read_applied_today() -> dict[str, dict]:
    """Latest action_log entry per object_id for today, non-dry, non-error."""
    entries = query_log(date=_today_ist(), limit=10_000)
    applied: dict[str, dict] = {}
    for e in reversed(entries):  # entries are DESC; reverse → ASC so latest overwrites
        if e.get("dry_run"):
            continue
        result = e.get("result") or ""
        if result.upper().startswith("ERROR"):
            continue
        if e.get("action") not in ("SET_BUDGET", "PAUSE"):
            continue
        applied[e["object_id"]] = e
    return applied


def _drift_label(current_cac: Optional[int], prev_cac: Optional[int]) -> str:
    if not prev_cac or not current_cac:
        return "HOLDING"
    delta_pct = (current_cac - prev_cac) / prev_cac * 100
    if abs(delta_pct) <= 5:
        return "HOLDING"
    return "IMPROVED" if delta_pct < 0 else "WORSENED"


# ── Main function ──────────────────────────────────────────────────────────────


async def summarize_accounts(
    account_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Port of summarizeAccount_. Returns accounts, drift_items, new_cache, overall."""
    rows = await fetch_dashboard(account_ids=account_ids)
    applied_today = _read_applied_today()
    prev_cache = read_cache()

    # Group rows by account
    by_account: dict[str, list] = {}
    for row in rows:
        by_account.setdefault(row["account"], []).append(row)

    account_summaries = []
    drift_items: list[dict] = []
    new_cache: dict[str, Any] = {}
    overall_spend = 0.0
    overall_results = 0.0
    overall_budget = 0

    slot = datetime.datetime.now(IST).strftime("%H:%M")

    for acct_name, acct_rows in by_account.items():
        spend_t = spend_y = spend_dby = 0.0
        results_t = results_y = 0.0
        total_budget = 0
        est_spend_after = 0
        scale_count = cut_count = pause_count = 0

        for row in acct_rows:
            oid = row["id"]
            t = row.get("today", {})
            y = row.get("yesterday", {})
            dby = row.get("day_before", {})
            budget = row["budget"]

            spend_t += float(t.get("spend", 0))
            spend_y += float(y.get("spend", 0))
            spend_dby += float(dby.get("spend", 0))
            results_t += float(t.get("results", 0))
            results_y += float(y.get("results", 0))
            total_budget += budget

            # Estimated spend after today's applied actions
            log_entry = applied_today.get(oid)
            if log_entry:
                if log_entry["action"] == "PAUSE":
                    est_spend_after += 0
                    pause_count += 1
                else:
                    nb = log_entry.get("new_budget") or budget
                    est_spend_after += nb
                    ob = log_entry.get("old_budget")
                    if nb and ob:
                        if nb > ob:
                            scale_count += 1
                        elif nb < ob:
                            cut_count += 1
            else:
                est_spend_after += budget

            # Drift (only for SET_BUDGET applied today)
            current_cac = t.get("cac")
            prev_entry = prev_cache.get(oid, {})
            prev_cac = prev_entry.get("cac") if isinstance(prev_entry, dict) else None

            if log_entry and log_entry["action"] == "SET_BUDGET":
                delta_pct = (
                    (current_cac - prev_cac) / prev_cac * 100 if prev_cac and current_cac else None
                )
                drift_items.append(
                    {
                        "object_id": oid,
                        "name": row["name"],
                        "account": acct_name,
                        "level": row["level"],
                        "drift": _drift_label(current_cac, prev_cac),
                        "prev_cac": prev_cac,
                        "current_cac": current_cac,
                        "delta_pct": delta_pct,
                    }
                )

            # Build new cache entry per object
            new_cache[oid] = {
                "cac": current_cac,
                "spend": int(float(t.get("spend", 0))),
                "cpi": t.get("cpi"),
            }

        blended_cac = round(spend_t / results_t) if results_t else None
        new_cache[f"__acct__:{acct_name}"] = {"cac": blended_cac, "slot": slot}

        overall_spend += spend_t
        overall_results += results_t
        overall_budget += total_budget

        account_summaries.append(
            {
                "account": acct_name,
                "spend_today": spend_t,
                "spend_yesterday": spend_y,
                "spend_day_before": spend_dby,
                "results_today": results_t,
                "results_yesterday": results_y,
                "total_daily_budget": total_budget,
                "est_spend_after_change": est_spend_after,
                "scale_count": scale_count,
                "cut_count": cut_count,
                "pause_count": pause_count,
                "blended_cac": blended_cac,
            }
        )

    overall_cac = round(overall_spend / overall_results) if overall_results else None
    new_cache["__overall__"] = {
        "cac": overall_cac,
        "slot": slot,
        "spend": int(overall_spend),
        "results": int(overall_results),
        "budget": overall_budget,
        "projCac": overall_cac,
    }

    return {
        "accounts": account_summaries,
        "drift_items": drift_items,
        "new_cache": new_cache,
        "overall_spend": overall_spend,
        "overall_results": overall_results,
        "overall_cac": overall_cac,
        "overall_budget": overall_budget,
    }
