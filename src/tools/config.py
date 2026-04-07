"""Application settings with validation."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Scanner configuration."""

    log_level: str = Field(
        default="INFO", description="Logging level (DEBUG, INFO, etc.)"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # === GitHub ===
    github_token: SecretStr = Field(
        default=...,
        description="GitHub personal access token for API rate limits",
    )
    github_api_url: str = Field(default="https://api.github.com")
    github_default_org: str = Field(default="opentelekomcloud-docs")
    github_default_branch: str = Field(default="main")

    # === Scanner ===
    rst_source_prefix: str = Field(
        default="api-ref/source/",
        description="Path prefix for RST files in docs repos",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
