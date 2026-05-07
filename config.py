import os
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Settings(BaseSettings):
    meta_access_token: str
    meta_api_version: str = "v21.0"

    owner_filter: str = "shashank"
    owner_filter_enabled: bool = True

    floor_budget: int = 1000
    cap_budget: int = 25000
    abo_pause_spend: int = 4000
    aaa_pause_spend: int = 4000
    cbo_pause_spend: int = 5000

    alert_cac_threshold: int = 300
    alert_budget_threshold: int = 3000

    max_retries: int = 5
    initial_backoff_ms: int = 2000
    batch_size: int = 25
    batch_sleep_ms: int = 1500

    data_dir: str = "./data"
    ist_tz: str = "Asia/Kolkata"

    model_config = SettingsConfigDict(env_file=os.path.join(BASE_DIR, ".env"), env_file_encoding="utf-8")


settings = Settings()