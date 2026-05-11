"""
애플리케이션 설정. 환경변수에서 값을 읽어 Settings 객체로 노출.
"""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 필수
    app_secret_key: str
    google_oauth_client_id: str
    google_oauth_client_secret: str

    # 선택 (기본값 있음)
    database_url: str = "sqlite:///./data/app.db"
    allowed_oauth_domain: str = ""
    allowed_oauth_emails: str = ""

    @property
    def allowed_oauth_domains(self) -> List[str]:
        return [d.strip() for d in self.allowed_oauth_domain.split(",") if d.strip()]

    @property
    def allowed_oauth_emails_list(self) -> List[str]:
        return [e.strip().lower() for e in self.allowed_oauth_emails.split(",") if e.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
