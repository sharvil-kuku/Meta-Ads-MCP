from typing import Optional

from constants import AAA_PAUSE_SPEND, ABO_PAUSE_SPEND, CAP, CBO_PAUSE_SPEND, FLOOR
from core.optimiser import clamp_budget


def check_pause_eligibility(
    structure: str,
    today_spend: int,
    current_budget: int,
) -> tuple[bool, Optional[str], Optional[int]]:
    """Check if pausing is safe given today's spend.

    Returns (eligible, fallback_action, fallback_budget).
    If eligible: (True, None, None).
    If not: (False, "SET_BUDGET", fallback_budget).
    """
    limits = {"ABO": ABO_PAUSE_SPEND, "AAA": AAA_PAUSE_SPEND, "CBO": CBO_PAUSE_SPEND}
    limit  = limits.get(structure, ABO_PAUSE_SPEND)
    if today_spend <= limit:
        return True, None, None
    cut50    = current_budget * 0.5
    spend    = max(today_spend, FLOOR)
    fallback = clamp_budget(min(cut50, spend))
    return False, "SET_BUDGET", fallback


def validate_budget(new_budget: int) -> tuple[bool, Optional[str]]:
    if new_budget <= 0:    return False, f"Budget must be positive; got {new_budget}"
    if new_budget < FLOOR: return False, f"Budget {new_budget} below floor {FLOOR}"
    if new_budget > CAP:   return False, f"Budget {new_budget} above cap {CAP}"
    return True, None
