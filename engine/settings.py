"""Engine-only settings, independent from app/config OAuth requirements."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    smartlead_api_key: str
    gemini_api_key: str
    control_sheet_url: str
    google_credentials_json: str

    bounce_warn: float = 0.05
    bounce_critical: float = 0.08
    min_bounce_sample: int = 50
    min_pass_rate: float = 0.40
    smartlead_daily_limit: int = 200

    state_db_url: str = "sqlite:///./data/state.db"


@lru_cache(maxsize=1)
def get_engine_settings() -> EngineSettings:
    return EngineSettings()  # type: ignore[call-arg]
