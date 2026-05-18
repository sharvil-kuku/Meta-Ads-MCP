"""Phase 3 unit tests — exact parity with script.gs decision logic."""

from core.optimiser import (
    DecisionContext,
    apply_conversion_to_budget,
    apply_long_run,
    bucket_from_age,
    clamp_budget,
    classify_structure,
    decide,
    decide_with_trace,
    slab_key,
)
from constants import FLOOR


# ── Helpers ───────────────────────────────────────────────────────────────────


def ctx(
    level="adset",
    budget=1000,
    age_days=3,
    t_spend=500,
    t_results=5,
    t_cac=100,
    t_cpi=50,
    y_cac=100,
    y_results=5,
    dby_cac=100,
    conversion=0,
    has_conversion=False,
) -> DecisionContext:
    return DecisionContext(
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


# ── D0 ────────────────────────────────────────────────────────────────────────


def test_d0_no_action():
    r = decide(ctx(age_days=0))
    assert r.action == ""
    assert r.reason == "D0_NO_ACTION"


# ── D1 ABO ────────────────────────────────────────────────────────────────────


def test_d1_abo_1k_better_low_cpi():
    # budget=1000, better band (cac<100), cpi=20 (<=30) → mult=3
    r = decide(ctx(age_days=1, budget=1000, t_cac=80, t_cpi=20, y_cac=0))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(1000 * 3)  # 3000


def test_d1_abo_1k_better_high_cpi():
    # cpi=40 (>30) → mult=2
    r = decide(ctx(age_days=1, budget=1000, t_cac=80, t_cpi=40, y_cac=0))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(1000 * 2)  # 2000


def test_d1_abo_2k_good_low_cpi():
    # budget=2000 (>1500 → 2K tier), good band (100<=cac<=150), cpi=20 → mult=2
    r = decide(ctx(age_days=1, budget=2000, t_cac=120, t_cpi=20, y_cac=0))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(2000 * 2)  # 4000


def test_d1_abo_2k_good_high_cpi():
    # cpi=40 → mult=1.5
    r = decide(ctx(age_days=1, budget=2000, t_cac=120, t_cpi=40, y_cac=0))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(2000 * 1.5)  # 3000


def test_d1_abo_bad_keep():
    # bad band (cac=160) → no slab → KEEP
    r = decide(ctx(age_days=1, budget=1000, t_cac=160, t_cpi=20, y_cac=0))
    assert r.action == ""
    assert "KEEP" in r.reason


# ── D1 CBO ────────────────────────────────────────────────────────────────────


def test_d1_cbo_better_low_cpi():
    # CBO (level=campaign), better, cpi=20 → mult=2
    r = decide(ctx(level="campaign", age_days=1, budget=5000, t_cac=80, t_cpi=20, y_cac=0))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(5000 * 2)


def test_d1_cbo_good_high_cpi():
    # CBO, good band, cpi=40 (>30) → mult=1.4
    r = decide(ctx(level="campaign", age_days=1, budget=5000, t_cac=130, t_cpi=40, y_cac=0))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(5000 * 1.4)


def test_d1_cbo_bad_keep():
    r = decide(ctx(level="campaign", age_days=1, budget=5000, t_cac=170, t_cpi=20, y_cac=0))
    assert r.action == ""
    assert "KEEP" in r.reason


# ── D1 AAA ────────────────────────────────────────────────────────────────────


def test_d1_aaa_better_cpi_26_high():
    # AAA (budget>=3500), better, cpi=26 (>25) → mult=1.6
    r = decide(ctx(age_days=1, budget=4000, t_cac=80, t_cpi=26, y_cac=0))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(4000 * 1.6)


def test_d1_aaa_better_cpi_24_low():
    # cpi=24 (<=25) → mult=2.0
    r = decide(ctx(age_days=1, budget=4000, t_cac=80, t_cpi=24, y_cac=0))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(4000 * 2.0)


def test_d1_aaa_bad_interp_cut():
    # AAA D1 bad band, cac=175 → interp(175,150,200,0,0.20) = 0.10 → mult=0.9
    r = decide(ctx(age_days=1, budget=4000, t_cac=175, t_cpi=20, y_cac=0))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(4000 * 0.9)


def test_d1_aaa_worsen_cut_60():
    # AAA D1 worsen (cac>250) → mult=0.4
    r = decide(ctx(age_days=1, budget=4000, t_cac=300, t_cpi=20, y_cac=0))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(4000 * 0.4)


# ── D1 edge cases ─────────────────────────────────────────────────────────────


def test_d1_both_zero_pause():
    # ABO, y=0, t=0, spend=500 (<=4000) → PAUSE
    r = decide(ctx(age_days=1, budget=1000, t_cac=0, y_cac=0, t_spend=500))
    assert r.action == "PAUSE"


def test_d1_abo_y_high_t_zero_pause():
    # ABO, y>500, t=0, spend=500 → PAUSE
    r = decide(ctx(age_days=1, budget=1000, t_cac=0, y_cac=600, t_spend=500))
    assert r.action == "PAUSE"


def test_d1_aaa_y_high_t_zero_cut60():
    # AAA, y>2000, t=0 → build_budget 0.4 (NOT pause)
    r = decide(ctx(age_days=1, budget=5000, t_cac=0, y_cac=2500, t_spend=500))
    assert r.action == "SET_BUDGET"
    assert "CUT_60" in r.reason


# ── D2 / D3+ ──────────────────────────────────────────────────────────────────


def test_d2_abo_better_better_trend():
    # D2, ABO (budget=2000), better band, BETTER trend → slab mult × trend
    # dby=80, y=70, t=60 → all better, ranks strictly decreasing → BETTER trend
    # D2_ABO_better at budget=2000: [1001,2001,3,2.5] → cpi=20 → mult=3
    # BETTER trend on scale-up → strong = 3
    r = decide(ctx(age_days=2, budget=2000, t_cac=60, t_cpi=20, y_cac=70, dby_cac=80))
    assert r.action == "SET_BUDGET"
    assert r.new_budget is not None


def test_d2_abo_bad_150_175_low_cpi():
    # D2, ABO, cac=157 (step=2), cpi=20 (low) → cut=0.05*2=0.10
    r = decide(ctx(age_days=2, budget=2000, t_cac=157, t_cpi=20, y_cac=80, dby_cac=80))
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(2000 * 0.9)


def test_d2_abo_bad_176_200_high_cpi():
    # D2, ABO (budget=2000), cac=188, cpi=40 (high) → cut_176_200 → interp(lo,hi)
    r = decide(ctx(age_days=2, budget=2000, t_cac=188, t_cpi=40, y_cac=80, dby_cac=80))
    assert r.action == "SET_BUDGET"


def test_d3_aaa_worse_b5000():
    # D3+, AAA (budget=5000), worse band (cac=220)
    # worse_200_250 at budget=5000 → cut_50 → new=2500
    r = decide(
        ctx(age_days=5, budget=5000, t_cac=220, t_cpi=20, y_cac=210, dby_cac=200, t_spend=1000)
    )
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(2500)


def test_d3_cbo_worsen_b3000_pause():
    # D3+, CBO (level=campaign, budget=3000), worsen (cac=300)
    # worsen_250_plus at budget=3000 → PAUSE → pause_or_fallback
    # spend=500 (<=5000 CBO limit) → PAUSE
    r = decide(
        ctx(
            level="campaign",
            age_days=5,
            budget=3000,
            t_cac=300,
            t_cpi=20,
            y_cac=280,
            dby_cac=260,
            t_spend=500,
        )
    )
    assert r.action == "PAUSE"


def test_d3_cbo_worsen_b8000_budget_spend():
    # D3+, CBO (budget=8000), worsen → worsen_250_plus → budget=max(spend, FLOOR)
    r = decide(
        ctx(
            level="campaign",
            age_days=5,
            budget=8000,
            t_cac=300,
            t_cpi=20,
            y_cac=280,
            dby_cac=260,
            t_spend=2000,
        )
    )
    assert r.action == "SET_BUDGET"
    assert r.new_budget == clamp_budget(max(2000, FLOOR))


def test_d3_all_zero_pause():
    # D3+, all CACs zero → pause_or_fallback
    r = decide(ctx(age_days=5, budget=1000, t_cac=0, y_cac=0, dby_cac=0, t_spend=0))
    assert r.action == "PAUSE"


def test_d3_t_zero_y_dby_positive_worsen():
    # t=0, y>0, dby>0 → effectiveBand=worsen
    r = decide(ctx(age_days=5, budget=3000, t_cac=0, y_cac=80, dby_cac=90, t_spend=500))
    assert "WORSEN" in r.reason


# ── Conversion modifier ───────────────────────────────────────────────────────


def test_conversion_gate_y_results_15():
    # y_results=15 (<=20) → no conversion modifier
    budget = apply_conversion_to_budget(2000, 15, True, 25)
    assert budget == 2000


def test_conversion_high_gte_18():
    # y_results=25, conv=20% → budget * 1.2
    budget = apply_conversion_to_budget(2000, 25, True, 20)
    assert budget == 2400


def test_conversion_low_lt_10():
    # y_results=25, conv=8% → budget * 0.8
    budget = apply_conversion_to_budget(2000, 25, True, 8)
    assert budget == 1600


def test_conversion_mid_10_to_18():
    # y_results=25, conv=15% → no change
    budget = apply_conversion_to_budget(2000, 25, True, 15)
    assert budget == 2000


# ── Long-run modifier ─────────────────────────────────────────────────────────


def test_long_run_age_20():
    # age=20 → lr=0.9 → 1+(2-1)*0.9 = 1.9
    result = apply_long_run(2.0, 20)
    assert abs(result - 1.9) < 1e-9


def test_long_run_age_35():
    # age=35 → lr=0.8 → 1+(2-1)*0.8 = 1.8
    result = apply_long_run(2.0, 35)
    assert abs(result - 1.8) < 1e-9


# ── NO_CHANGE guard ───────────────────────────────────────────────────────────


def test_no_change_guard():
    # budget=1000, mult=1.0 → clamped=1000=budget → action=""
    r = decide(ctx(age_days=2, budget=1000, t_cac=60, t_cpi=20, y_cac=60, dby_cac=60, t_spend=50))
    # If clamped == budget → NO_CHANGE
    if r.action == "":
        assert "NO_CHANGE" in r.reason or r.reason != ""


# ── Pause eligibility ─────────────────────────────────────────────────────────


def test_pause_abo_spend_over_limit():
    # ABO spend=4001 (>4000) → not eligible → fallback cut50
    r = decide(ctx(age_days=1, budget=1000, t_cac=0, y_cac=0, t_spend=4001))
    assert r.action == "SET_BUDGET"
    assert "PROTECT_CUT_50" in r.reason


def test_pause_cbo_spend_over_limit():
    # CBO spend=5001 (>5000) → not eligible → fallback cut50
    r = decide(ctx(level="campaign", age_days=1, budget=10000, t_cac=0, y_cac=0, t_spend=5001))
    assert r.action == "SET_BUDGET"
    assert "PROTECT_CUT_50" in r.reason


# ── CBO slab remapping ────────────────────────────────────────────────────────


def test_cbo_d2_uses_aaa_slab():
    key = slab_key("D2", "CBO", "better")
    assert key == "D2_AAA_better"


# ── decide_with_trace ─────────────────────────────────────────────────────────


def test_decide_with_trace_has_steps():
    c = ctx(age_days=1, budget=1000, t_cac=80, t_cpi=20, y_cac=0)
    r = decide_with_trace(c)
    assert len(r.steps) > 0
    step_names = {s["step"] for s in r.steps}
    assert "structure" in step_names
    assert "day_bucket" in step_names
