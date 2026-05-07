import datetime
import math
from dataclasses import dataclass, field
from typing import Optional

import pytz

from constants import (
    AAA_PAUSE_SPEND,
    ABO_PAUSE_SPEND,
    CAP,
    CBO_PAUSE_SPEND,
    FLOOR,
    SCALE_SLABS,
)


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class DecisionContext:
    level:          str       # "campaign" or "adset"
    structure:      str       # "ABO", "AAA", "CBO"
    day_bucket:     str       # "D0", "D1", "D2", "D3+"
    age_days:       int
    budget:         int       # current daily budget (INR)
    t_spend:        float
    t_results:      float
    t_cac:          float
    t_cpi:          float
    y_cac:          float
    y_results:      float     # for conversion gate
    dby_cac:        float
    conversion:     float     # raw value; accepts 0.25 or 25 for 25%
    has_conversion: bool


@dataclass
class DecisionResult:
    action:     str           # "SET_BUDGET", "PAUSE", or "" (no action)
    new_budget: Optional[int]
    reason:     str
    steps:      list = field(default_factory=list)


# ── Classification ─────────────────────────────────────────────────────────────

def classify_structure(level: str, daily_budget: int) -> str:
    if level == "campaign":
        return "CBO"
    return "AAA" if daily_budget >= 3500 else "ABO"  # >= 3500, not > 3500


def compute_age_days(start_time: str | None, today: datetime.date) -> int:
    if not start_time:
        return 9999
    try:
        # Meta returns e.g. "2024-01-15T00:00:00+0000" or "2024-01-15T00:00:00+0530"
        dt = datetime.datetime.fromisoformat(
            start_time.replace("+0000", "+00:00").replace("Z", "+00:00")
        )
        return (today - dt.date()).days
    except Exception:
        return 9999


def bucket_from_age(age_days: int) -> str:
    if age_days == 0: return "D0"
    if age_days == 1: return "D1"
    if age_days == 2: return "D2"
    return "D3+"


# ── CAC band ──────────────────────────────────────────────────────────────────

def cac_band(cac: float) -> str:
    if not cac or cac <= 0: return "zero"
    if cac < 100:           return "better"
    if cac <= 150:          return "good"
    if cac <= 200:          return "bad"
    if cac <= 250:          return "worse"
    return "worsen"


BAND_RANK: dict[str, int] = {
    "zero": -1, "better": 0, "good": 1, "bad": 2, "worse": 3, "worsen": 4,
}


# ── Trend classification ───────────────────────────────────────────────────────

def classify_trend(dby: float, y: float, today: float) -> str:
    b_dby = cac_band(dby)
    b_y   = cac_band(y)
    b_t   = cac_band(today)

    if b_dby == "zero" or b_y == "zero" or b_t == "zero":
        return "INSUFFICIENT"

    prev_good  = (b_dby in ("better", "good")) and (b_y in ("better", "good"))
    prev_bad   = (b_dby in ("bad", "worse", "worsen")) and (b_y in ("bad", "worse", "worsen"))
    today_good = b_t in ("better", "good")
    today_bad  = b_t in ("bad", "worse", "worsen")

    if prev_good and today_bad:  return "GOOD_THEN_BAD"
    if prev_bad  and today_good: return "BAD_THEN_GOOD"

    r_dby, r_y, r_t = BAND_RANK[b_dby], BAND_RANK[b_y], BAND_RANK[b_t]

    if (r_dby > r_y > r_t) or (r_dby >= r_y >= r_t and r_t < r_dby):
        return "BETTER"

    prev_avg = (dby + y) / 2
    if abs(today - prev_avg) <= 10:
        return "MAINTAINING"

    jump = r_t - r_dby
    if jump >= 2:  return "WORSEN"
    if jump == 1:  return "WORSE"
    return "MAINTAINING"


# ── Slab lookup ────────────────────────────────────────────────────────────────

def slab_key(day_bucket: str, structure: str, band: str) -> str:
    s = "AAA" if structure == "CBO" else structure   # CBO → AAA slabs for D2/D3+
    return f"{day_bucket}_{s}_{band}"


def lookup_slab(key: str, budget: int) -> list | None:
    table = SCALE_SLABS.get(key)
    if not table:
        return None
    for row in table:
        if row[0] <= budget < row[1]:
            return row
    return None


def get_scale_mult(key: str, budget: int, t_cpi: float) -> float | None:
    s = lookup_slab(key, budget)
    if s is None:
        return None
    return s[3] if t_cpi > 30 else s[2]
    # AAA D1 "better" CPI threshold of 25 handled in _decide_impl directly


# ── Trend modifier ─────────────────────────────────────────────────────────────

def apply_trend(mult: float, trend: str) -> float:
    is_up   = mult > 1
    is_down = mult < 1
    strong  = mult
    mild    = (1 + (mult - 1) * 0.5) if is_up else (1 - (1 - mult) * 0.5) if is_down else 1.0

    match trend:
        case "BETTER":        return strong if is_up   else mild
        case "MAINTAINING":   return mild
        case "WORSE":         return mild
        case "WORSEN":        return strong if is_down else mild
        case "GOOD_THEN_BAD": return mild   if is_down else 0.9
        case "BAD_THEN_GOOD": return mild   if is_up   else 1.1
        case "INSUFFICIENT":  return mult
        case _:               return mult


# ── Long-run modifier ──────────────────────────────────────────────────────────

def long_run_modifier(age_days: int) -> float:
    if age_days <= 14: return 1.0
    if age_days <= 30: return 0.9
    return 0.8


def apply_long_run(mult: float, age_days: int) -> float:
    lr = long_run_modifier(age_days)
    return 1 + (mult - 1) * lr  # scales the delta from 1, NOT simple multiplication


# ── Conversion modifier ────────────────────────────────────────────────────────

def apply_conversion_to_budget(budget: float, y_results: float,
                                has_conversion: bool, conversion_raw: float) -> float:
    if not has_conversion:
        return budget
    if y_results <= 20:      # gate: strictly > 20
        return budget

    conv_pct = conversion_raw
    if 0 < conv_pct <= 1:    # normalize: 0.25 → 25
        conv_pct *= 100
    if conv_pct <= 0:
        return budget

    if conv_pct >= 18: return budget * 1.2
    if conv_pct >= 10: return budget
    return budget * 0.8


def conversion_tag(raw_budget: float, final_budget: float) -> str:
    if round(raw_budget) == round(final_budget): return ""
    return "_CONV_HIGH_X1_2" if final_budget > raw_budget else "_CONV_LOW_X0_8"


# ── Clamp budget ───────────────────────────────────────────────────────────────

def clamp_budget(v: float) -> int:
    if not math.isfinite(v) or v <= 0:
        return FLOOR
    r = round(v / 100) * 100
    r = min(r, CAP)
    r = max(r, FLOOR)
    return r


# ── Pause eligibility ──────────────────────────────────────────────────────────

def can_pause(structure: str, t_spend: float) -> bool:
    limit = {"CBO": CBO_PAUSE_SPEND, "AAA": AAA_PAUSE_SPEND}.get(structure, ABO_PAUSE_SPEND)
    return t_spend <= limit


# ── Cut curve helpers ──────────────────────────────────────────────────────────

def interp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0: return y0
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def low_end_cut(structure: str, day_bucket: str, b: int) -> float:
    if b <= 1000: return 0
    if b <= 2000: return 0.50

    if structure == "ABO":
        if b <= 3000: return 0.30
        if b <= 5000: return 0.30
        if day_bucket == "D3+":
            if b <= 10000: return 0.00
            if b <= 20000: return 0.30
            if b <= 25000: return 0.40
        else:  # D2
            if b <= 10000: return 0.30
        return 0.50
    # AAA / CBO
    if day_bucket == "D3+":
        if b <= 3000:  return 0.20
        if b <= 5000:  return 0.25
        if b <= 10000: return 0.30
    else:  # D2
        if b <= 3000:  return 0.30
        if b <= 5000:  return 0.30
        if b <= 10000: return 0.30
    return 0.50


def high_end_cut(structure: str, day_bucket: str, b: int) -> float:
    if b <= 1000: return 0
    if b <= 2000: return 0.50

    if structure == "ABO":
        if b <= 3000: return 0.65
        if b <= 5000: return 0.60
        if day_bucket == "D3+":
            if b <= 10000: return 0.30
            if b <= 20000: return 0.50
            if b <= 25000: return 0.60
        else:  # D2
            if b <= 10000: return 0.50
        return 0.50
    # AAA / CBO
    if day_bucket == "D3+":
        if b <= 3000:  return 0.50
        if b <= 5000:  return 0.55
        if b <= 10000: return 0.60
    else:  # D2
        if b <= 3000:  return 0.65
        if b <= 5000:  return 0.60
        if b <= 10000: return 0.50
    return 0.50


def cut_150_175(cac: float, t_cpi: float, structure: str, day_bucket: str, b: int) -> float:
    cpi_low = t_cpi <= 30
    if cac < 155:    step = 1
    elif cac < 160:  step = 2
    elif cac < 165:  step = 3
    elif cac < 170:  step = 4
    else:            step = 5
    frac = step / 5

    if b <= 1000: return 0
    if cpi_low:   return 0.05 * step
    return low_end_cut(structure, day_bucket, b) * frac


def cut_176_200(cac: float, t_cpi: float, structure: str, day_bucket: str, b: int) -> float:
    cpi_low = t_cpi <= 30
    if b <= 1000: return 0
    if cpi_low:   return 0.25
    lo = low_end_cut(structure, day_bucket, b)
    hi = high_end_cut(structure, day_bucket, b)
    return interp(cac, 176, 200, lo, hi)


# ── High-CAC helpers ───────────────────────────────────────────────────────────

def worse_200_250(budget: int, t_spend: float) -> dict:
    if budget <= 4000:  return {"action": "SET_BUDGET", "new_budget": max(t_spend, FLOOR), "reason": "budget=amount_spent"}
    if budget <= 10000: return {"action": "SET_BUDGET", "new_budget": budget * 0.5,         "reason": "cut_50"}
    if budget <= 15000: return {"action": "SET_BUDGET", "new_budget": budget * 0.6,         "reason": "cut_40"}
    if budget <= 20000: return {"action": "SET_BUDGET", "new_budget": budget * 0.65,        "reason": "cut_35"}
    return                     {"action": "SET_BUDGET", "new_budget": budget * 0.7,         "reason": "cut_30"}


def worsen_250_plus(budget: int, t_spend: float) -> dict:
    if budget <= 4000:  return {"action": "PAUSE",      "new_budget": None,                 "reason": "pause"}
    if budget <= 10000: return {"action": "SET_BUDGET",  "new_budget": max(t_spend, FLOOR), "reason": "budget=amount_spent"}
    if budget <= 15000: return {"action": "SET_BUDGET",  "new_budget": budget * 0.4,        "reason": "cut_60"}
    if budget <= 20000: return {"action": "SET_BUDGET",  "new_budget": budget * 0.5,        "reason": "cut_50"}
    return                     {"action": "SET_BUDGET",  "new_budget": budget * 0.6,        "reason": "cut_40"}


# ── Pipeline helpers ───────────────────────────────────────────────────────────

def _step(steps: list | None, label: str, value: str) -> None:
    if steps is not None:
        steps.append({"step": label, "value": value})


def _result(action: str, new_budget: int | None, reason: str,
            steps: list | None) -> DecisionResult:
    return DecisionResult(action=action, new_budget=new_budget,
                          reason=reason, steps=steps or [])


def _build_budget_decision(ctx: DecisionContext, base_mult: float,
                            reason_base: str, steps: list | None) -> DecisionResult:
    _step(steps, "base_mult", str(base_mult))
    lr_mult    = apply_long_run(base_mult, ctx.age_days)
    _step(steps, "lr_mult", str(lr_mult))
    rec        = ctx.budget * lr_mult
    after_conv = apply_conversion_to_budget(rec, ctx.y_results,
                                            ctx.has_conversion, ctx.conversion)
    tag        = conversion_tag(rec, after_conv)
    clamped    = clamp_budget(after_conv)
    _step(steps, "clamped", str(clamped))

    if clamped == round(ctx.budget):
        return _result("", None, reason_base + tag + "_NO_CHANGE", steps)
    return _result("SET_BUDGET", clamped, reason_base + tag, steps)


def _pause_or_fallback(ctx: DecisionContext, reason_base: str,
                        steps: list | None) -> DecisionResult:
    if can_pause(ctx.structure, ctx.t_spend):
        _step(steps, "pause_eligible", "true")
        return _result("PAUSE", None, reason_base + "_PAUSE", steps)
    _step(steps, "pause_eligible", "false")
    cut50    = ctx.budget * 0.5
    spend    = max(ctx.t_spend, FLOOR)
    fallback = clamp_budget(min(cut50, spend))
    return _result("SET_BUDGET", fallback, reason_base + "_PROTECT_CUT_50", steps)


# ── Master decide() ────────────────────────────────────────────────────────────

def decide(ctx: DecisionContext) -> DecisionResult:
    return _decide_impl(ctx, steps=None)


def decide_with_trace(ctx: DecisionContext) -> DecisionResult:
    steps: list = []
    _step(steps, "structure",  ctx.structure)
    _step(steps, "day_bucket", ctx.day_bucket)
    _step(steps, "age_days",   str(ctx.age_days))
    _step(steps, "budget",     str(ctx.budget))
    _step(steps, "t_cac",      str(ctx.t_cac))
    _step(steps, "t_cpi",      str(ctx.t_cpi))
    _step(steps, "y_cac",      str(ctx.y_cac))
    _step(steps, "dby_cac",    str(ctx.dby_cac))
    return _decide_impl(ctx, steps=steps)


def _decide_impl(ctx: DecisionContext, steps: list | None) -> DecisionResult:
    s  = ctx.structure
    db = ctx.day_bucket

    # ── D0 ────────────────────────────────────────────────────────────────────
    if db == "D0":
        return _result("", None, "D0_NO_ACTION", steps)

    # ── D1 ────────────────────────────────────────────────────────────────────
    if db == "D1":
        y, t = ctx.y_cac, ctx.t_cac

        if y == 0 and t == 0:
            return _pause_or_fallback(ctx, f"{s}_D1_BOTH_ZERO", steps)

        if s == "ABO" and y > 500  and t == 0:
            return _pause_or_fallback(ctx, "ABO_D1_D0_HIGH_D1_ZERO", steps)
        if s == "CBO" and y > 2000 and t == 0:
            return _pause_or_fallback(ctx, "CBO_D1_D0_HIGH_D1_ZERO", steps)
        if s == "AAA" and y > 2000 and t == 0:
            return _build_budget_decision(ctx, 0.4, "AAA_D1_D0_HIGH_D1_ZERO_CUT_60", steps)

        band = cac_band(t)
        _step(steps, "band", band)

        if band == "zero":
            return _result("", None, f"{s}_D1_T_ZERO_HOLD", steps)

        if s == "ABO":
            tier = "1K" if ctx.budget <= 1500 else "2K"
            key  = f"D1_ABO_{tier}_{band}"
            _step(steps, "slab_key", key)
            mult = get_scale_mult(key, ctx.budget, ctx.t_cpi)
            if mult is not None:
                return _build_budget_decision(ctx, mult, f"ABO_D1_{tier}_{band.upper()}", steps)
            return _result("", None, f"ABO_D1_{band.upper()}_KEEP", steps)

        if s == "CBO":
            if band == "better":
                mult = 1.6 if ctx.t_cpi > 30 else 2.0
                return _build_budget_decision(ctx, mult, "CBO_D1_BETTER", steps)
            if band == "good":
                mult = 1.4 if ctx.t_cpi > 30 else interp(t, 100, 150, 2.0, 1.6)
                return _build_budget_decision(ctx, mult, "CBO_D1_GOOD", steps)
            return _result("", None, f"CBO_D1_{band.upper()}_KEEP", steps)

        if s == "AAA":
            if band == "better":
                mult = 1.6 if ctx.t_cpi > 25 else 2.0   # AAA D1: threshold is 25, not 30
                return _build_budget_decision(ctx, mult, "AAA_D1_BETTER", steps)
            if band == "good":
                mult = 1.4 if ctx.t_cpi > 30 else interp(t, 100, 150, 2.0, 1.6)
                return _build_budget_decision(ctx, mult, "AAA_D1_GOOD", steps)
            if band == "bad":
                cut = interp(t, 150, 200, 0, 0.20)
                return _build_budget_decision(ctx, 1 - cut, f"AAA_D1_BAD_CUT_{round(cut*100)}", steps)
            if band == "worse":
                cut = interp(t, 200, 250, 0.20, 0.40)
                return _build_budget_decision(ctx, 1 - cut, f"AAA_D1_WORSE_CUT_{round(cut*100)}", steps)
            if band == "worsen":
                return _build_budget_decision(ctx, 0.4, "AAA_D1_WORSEN_CUT_60", steps)

        return _result("", None, f"{s}_D1_{band.upper()}_KEEP", steps)

    # ── D2 / D3+ ──────────────────────────────────────────────────────────────
    if db in ("D2", "D3+"):
        t, y, dby = ctx.t_cac, ctx.y_cac, ctx.dby_cac

        if t == 0 and y == 0 and dby == 0:
            return _pause_or_fallback(ctx, f"{s}_{db}_ALL_ZERO", steps)
        if dby > 250 and y == 0 and t == 0:
            return _pause_or_fallback(ctx, f"{s}_{db}_DBY_HIGH_REST_ZERO", steps)
        if dby > 250 and y > 250 and t == 0:
            return _pause_or_fallback(ctx, f"{s}_{db}_DBY_Y_HIGH_T_ZERO", steps)

        if t == 0 and y > 0 and dby > 0:
            effective_band = "worsen"
        else:
            effective_band = cac_band(t)

        _step(steps, "effective_band", effective_band)

        if effective_band == "zero":
            return _result("", None, f"{s}_{db}_T_ZERO_HOLD", steps)

        trend = classify_trend(dby, y, t)
        _step(steps, "trend", trend)

        if effective_band == "worsen":
            r = worsen_250_plus(ctx.budget, ctx.t_spend)
            if r["action"] == "PAUSE":
                return _pause_or_fallback(ctx, f"{s}_{db}_WORSEN", steps)
            mult = r["new_budget"] / ctx.budget
            return _build_budget_decision(ctx, mult, f"{s}_{db}_WORSEN_{r['reason']}", steps)

        if effective_band == "worse":
            r = worse_200_250(ctx.budget, ctx.t_spend)
            mult = r["new_budget"] / ctx.budget
            return _build_budget_decision(ctx, mult, f"{s}_{db}_WORSE_{r['reason']}", steps)

        if effective_band == "bad":
            if t <= 175:
                cut = cut_150_175(t, ctx.t_cpi, s, db, ctx.budget)
                if cut == 0:
                    return _result("", None, f"{s}_{db}_BAD_150_175_KEEP", steps)
                return _build_budget_decision(ctx, 1 - cut,
                                              f"{s}_{db}_BAD_150_175_CUT_{round(cut*100)}", steps)
            else:
                cut = cut_176_200(t, ctx.t_cpi, s, db, ctx.budget)
                if cut == 0:
                    return _result("", None, f"{s}_{db}_BAD_176_200_KEEP", steps)
                return _build_budget_decision(ctx, 1 - cut,
                                              f"{s}_{db}_BAD_176_200_CUT_{round(cut*100)}", steps)

        key = slab_key(db, s, effective_band)
        _step(steps, "slab_key", key)
        base_mult = get_scale_mult(key, ctx.budget, ctx.t_cpi)
        if base_mult is None:
            return _result("", None, f"{s}_{db}_NO_SLAB_HOLD", steps)

        trend_mult = apply_trend(base_mult, trend)
        _step(steps, "trend_mult", str(trend_mult))
        return _build_budget_decision(ctx, trend_mult,
                                      f"{s}_{db}_{effective_band.upper()}_TREND_{trend}", steps)

    return _result("", None, f"{s}_{db}_NO_MATCH", steps)


# ── Context builder from dashboard row ────────────────────────────────────────

def ctx_from_row(row: dict, tz_str: str = "Asia/Kolkata") -> DecisionContext:
    tz    = pytz.timezone(tz_str)
    today = datetime.datetime.now(tz).date()

    budget    = row["budget"]
    level     = row["level"]
    structure = classify_structure(level, budget)
    age       = compute_age_days(row.get("start_time"), today)
    day_bkt   = bucket_from_age(age)

    t   = row.get("today",      {})
    y   = row.get("yesterday",  {})
    dby = row.get("day_before", {})

    t_spend    = float(t.get("spend",    0))
    t_results  = float(t.get("results",  0))
    t_installs = float(t.get("installs", 0))
    t_cac      = float(t.get("cac") or 0)
    t_cpi      = round(t_spend / t_installs) if t_installs else 0
    y_cac      = float(y.get("cac") or 0)
    y_results  = float(y.get("results",  0))
    dby_cac    = float(dby.get("cac") or 0)

    return DecisionContext(
        level=level,
        structure=structure,
        day_bucket=day_bkt,
        age_days=age,
        budget=budget,
        t_spend=t_spend,
        t_results=t_results,
        t_cac=t_cac,
        t_cpi=t_cpi,
        y_cac=y_cac,
        y_results=y_results,
        dby_cac=dby_cac,
        conversion=0,
        has_conversion=False,
    )
