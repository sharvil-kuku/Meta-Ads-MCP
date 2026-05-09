from pydantic import BaseModel


# ── Account tools ──────────────────────────────────────────────────────────────

class CheckTokenInput(BaseModel):
    pass


class ListAdAccountsInput(BaseModel):
    limit: int = 200


# ── Data tools ─────────────────────────────────────────────────────────────────

class GetDashboardSnapshotInput(BaseModel):
    account_ids: list[str] | None = None


class GetInsightsInput(BaseModel):
    object_id: str
    level: str = "adset"   # "campaign" or "adset"


# ── Optimiser tools ────────────────────────────────────────────────────────────

class RunOptimiserInput(BaseModel):
    account_ids: list[str] | None = None
    dry_run: bool = True


class ExplainDecisionInput(BaseModel):
    object_id: str
    level: str = "adset"
    # Optional: pass metrics directly to skip live API call
    t_spend: float | None = None
    t_results: float | None = None
    t_cac: float | None = None
    t_cpi: float | None = None
    y_cac: float | None = None
    y_results: float | None = None
    dby_cac: float | None = None
    budget: int | None = None
    age_days: int | None = None
    conversion: float = 0
    has_conversion: bool = False


class SimulateBudgetChangeInput(BaseModel):
    level: str                    # "campaign" or "adset"
    budget: int
    t_spend: float
    t_results: float
    t_cac: float
    t_cpi: float
    y_cac: float
    y_results: float
    dby_cac: float
    age_days: int
    conversion: float = 0
    has_conversion: bool = False


# ── Write tools ────────────────────────────────────────────────────────────────

class ApplyBudgetChangeInput(BaseModel):
    object_id: str
    level: str                    # "campaign" or "adset"
    new_budget: int
    dry_run: bool = True


class PauseObjectInput(BaseModel):
    object_id: str
    level: str                    # "campaign" or "adset"
    dry_run: bool = True


class BulkChange(BaseModel):
    object_id: str
    level: str
    action: str                   # "SET_BUDGET" or "PAUSE"
    new_budget: int | None = None


class BulkApplyChangesInput(BaseModel):
    changes: list[BulkChange]
    dry_run: bool = True


# ── Report tools ───────────────────────────────────────────────────────────────

class GetAlertsInput(BaseModel):
    account_ids: list[str] | None = None


class GetReportSnapshotInput(BaseModel):
    account_ids: list[str] | None = None


class GetDriftAnalysisInput(BaseModel):
    account_ids: list[str] | None = None


class GetActionLogInput(BaseModel):
    date: str | None = None       # YYYY-MM-DD in IST; defaults to today
    account: str | None = None
    action_type: str | None = None
    limit: int = 50


# ── Campaign tools ───────────────────────────────────────────────────────────────

class CreateCampaignInput(BaseModel):
    account_id: str
    name: str
    objective: str = "OUTCOME_TRAFFIC"  # OUTCOME_TRAFFIC, OUTCOME_CONVERSIONS, OUTCOME_REACH, etc.
    status: str = "PAUSED"               # PAUSED, ACTIVE
    daily_budget: int | None = None
    special_ad_categories: list[str] = []


class GetCampaignInput(BaseModel):
    campaign_id: str
    fields: list[str] = ["id", "name", "status", "objective", "daily_budget", "created_time"]


class ListCampaignsInput(BaseModel):
    account_id: str
    status_filter: str | None = None  # ACTIVE, PAUSED
    limit: int = 100


class UpdateCampaignInput(BaseModel):
    campaign_id: str
    name: str | None = None
    status: str | None = None
    daily_budget: int | None = None


class DeleteCampaignInput(BaseModel):
    campaign_id: str


# ── AdSet tools ────────────────────────────────────────────────────────────────

class CreateAdSetInput(BaseModel):
    campaign_id: str
    name: str
    daily_budget: int
    billing_event: str = "IMPRESSIONS"  # IMPRESSIONS, CLICKS, CONVERSIONS
    optimization_goal: str = "LINK_CLICKS"
    bid_amount: int | None = None
    status: str = "PAUSED"
    targeting: dict | None = None


class GetAdSetInput(BaseModel):
    adset_id: str
    fields: list[str] = ["id", "name", "status", "daily_budget", "campaign_id", "targeting"]


class ListAdSetsInput(BaseModel):
    campaign_id: str
    status_filter: str | None = None
    limit: int = 100


class UpdateAdSetInput(BaseModel):
    adset_id: str
    name: str | None = None
    status: str | None = None
    daily_budget: int | None = None
    bid_amount: int | None = None


class DeleteAdSetInput(BaseModel):
    adset_id: str
