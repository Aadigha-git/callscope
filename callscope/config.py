"""Typed application settings loaded from environment variables (prefix CALLSCOPE_)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    DEMO = "demo"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CALLSCOPE_", env_file=".env", extra="ignore", case_sensitive=False
    )

    env: Env = Env.DEV
    log_level: str = "INFO"
    log_json: bool = True
    metrics_port: int = 9100

    database_url: str = "postgresql://callscope:callscope_dev@127.0.0.1:5432/callscope"
    s3_endpoint: str = "http://127.0.0.1:9000"
    s3_bucket: str = "callscope"

    hermes_base_url: str = "http://127.0.0.1:8642"
    hermes_api_key: SecretStr = SecretStr("changeme-local-only")

    livekit_url: str = "ws://127.0.0.1:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: SecretStr = SecretStr("devsecret-change-me-min-32-chars-long")

    captcha_secret: SecretStr = SecretStr("")

    @property
    def is_production_like(self) -> bool:
        return self.env in (Env.STAGING, Env.DEMO)


@lru_cache
def get_settings() -> Settings:
    return Settings()
