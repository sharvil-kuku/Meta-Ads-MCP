from typing import Optional

from pydantic import BaseModel


# ── Account tools ──────────────────────────────────────────────────────────────

class CheckTokenOutput(BaseModel):
    valid: bool
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    error: Optional[str] = None


class AdAccountOutput(BaseModel):
    id: str
    account_id: str
    name: str
    account_status: str
    currency: str


class ListAdAccountsOutput(BaseModel):
    accounts: list[AdAccountOutput]
    count: int


# ── Data tools ─────────────────────────────────────────────────────────────────

class DayInsights(BaseModel):
    spend: float = 0
    results: float = 0
    installs: float = 0
    cac: Optional[int] = None
    cpi: Optional[int] = None


class DashboardRow(BaseModel):
    id: str
    name: str
    account: str
    account_id: str
    level: str                    # "campaign" or "adset"
    status: str
    budget: int
    type: str                     # "App" or "Web"
    start_time: Optional[str] = None
    today: DayInsights = DayInsights()
    yesterday: DayInsights = DayInsights()
    day_before: DayInsights = DayInsights()


class DashboardSnapshotOutput(BaseModel):
    rows: list[DashboardRow]
    count: int


class InsightsOutput(BaseModel):
    object_id: str
    today: DayInsights
    yesterday: DayInsights
    day_before: DayInsights


# ── Optimiser tools ────────────────────────────────────────────────────────────

class OptimiserRecommendation(BaseModel):
    object_id: str
    name: str
    account: str
    level: str
    structure: str                # "ABO", "AAA", "CBO"
    day_bucket: str               # "D0", "D1", "D2", "D3+"
    action: str                   # "SET_BUDGET", "PAUSE", or "" (no action)
    current_budget: int
    new_budget: Optional[int] = None
    reason: str
    today_cac: Optional[int] = None
    today_spend: float = 0


class RunOptimiserOutput(BaseModel):
    recommendations: list[OptimiserRecommendation]
    count: int
    dry_run: bool = True


class DecisionStep(BaseModel):
    step: str
    value: str


class ExplainDecisionOutput(BaseModel):
    object_id: str
    action: str
    new_budget: Optional[int] = None
    reason: str
    steps: list[DecisionStep]


class SimulateBudgetChangeOutput(BaseModel):
    action: str
    new_budget: Optional[int] = None
    reason: str
    steps: list[DecisionStep]


# ── Write tools ────────────────────────────────────────────────────────────────

class ApplyBudgetChangeOutput(BaseModel):
    success: bool
    object_id: str
    action_taken: str
    old_budget: Optional[int] = None
    new_budget: Optional[int] = None
    dry_run: bool
    error: Optional[str] = None


class PauseObjectOutput(BaseModel):
    success: bool
    object_id: str
    action_taken: str
    dry_run: bool
    error: Optional[str] = None


class BulkChangeResult(BaseModel):
    object_id: str
    action_taken: str
    success: bool
    error: Optional[str] = None


class BulkApplyChangesOutput(BaseModel):
    results: list[BulkChangeResult]
    success_count: int
    error_count: int
    dry_run: bool


# ── Report tools ───────────────────────────────────────────────────────────────

class AlertItem(BaseModel):
    object_id: str
    name: str
    account: str
    level: str
    alert_type: str               # "HIGH_CAC", "HIGH_BUDGET", or "HIGH_CAC_AND_BUDGET"
    cac: Optional[int] = None
    budget: int = 0
    today_spend: float = 0


class GetAlertsOutput(BaseModel):
    alerts: list[AlertItem]
    count: int


class AccountSummary(BaseModel):
    account: str
    spend_today: float = 0
    spend_yesterday: float = 0
    spend_day_before: float = 0
    results_today: float = 0
    results_yesterday: float = 0
    total_daily_budget: int = 0
    est_spend_after_change: int = 0
    scale_count: int = 0
    cut_count: int = 0
    pause_count: int = 0
    blended_cac: Optional[int] = None


class GetReportSnapshotOutput(BaseModel):
    accounts: list[AccountSummary]
    overall_spend: float = 0
    overall_results: float = 0
    overall_cac: Optional[int] = None
    overall_budget: int = 0


class DriftItem(BaseModel):
    object_id: str
    name: str
    account: str
    level: str
    drift: str                    # "IMPROVED", "WORSENED", "HOLDING"
    prev_cac: Optional[int] = None
    current_cac: Optional[int] = None
    delta_pct: Optional[float] = None


class GetDriftAnalysisOutput(BaseModel):
    items: list[DriftItem]
    count: int


class ActionLogEntry(BaseModel):
    id: int
    timestamp: str
    account: Optional[str] = None
    object_id: str
    level: str
    name: Optional[str] = None
    action: str
    old_budget: Optional[int] = None
    new_budget: Optional[int] = None
    cac_at_apply: Optional[int] = None
    spend_at_apply: Optional[int] = None
    result: Optional[str] = None
    dry_run: bool


class GetActionLogOutput(BaseModel):
    entries: list[ActionLogEntry]
    count: int


# ── Campaign tools ───────────────────────────────────────────────────────────────

class CampaignOutput(BaseModel):
    id: str
    name: str
    status: str
    objective: str
    daily_budget: int | None = None
    created_time: str | None = None


class CreateCampaignOutput(BaseModel):
    success: bool
    campaign_id: str | None = None
    error: str | None = None


class GetCampaignOutput(BaseModel):
    campaign: CampaignOutput | None = None
    error: str | None = None


class ListCampaignsOutput(BaseModel):
    campaigns: list[CampaignOutput]
    count: int


class UpdateCampaignOutput(BaseModel):
    success: bool
    campaign_id: str
    error: str | None = None


class DeleteCampaignOutput(BaseModel):
    success: bool
    campaign_id: str
    error: str | None = None


# ── AdSet tools ────────────────────────────────────────────────────────────────

class AdSetOutput(BaseModel):
    id: str
    name: str
    status: str
    campaign_id: str
    daily_budget: int | None = None
    bid_amount: int | None = None
    targeting: dict | None = None


class CreateAdSetOutput(BaseModel):
    success: bool
    adset_id: str | None = None
    error: str | None = None


class GetAdSetOutput(BaseModel):
    adset: AdSetOutput | None = None
    error: str | None = None


class ListAdSetsOutput(BaseModel):
    adsets: list[AdSetOutput]
    count: int


class UpdateAdSetOutput(BaseModel):
    success: bool
    adset_id: str
    error: str | None = None


class DeleteAdSetOutput(BaseModel):
    success: bool
    adset_id: str
    error: str | None = None
