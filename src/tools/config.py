"""Application settings with validation.

Configuration sources, in order of precedence (highest first):
  1. Constructor kwargs (programmatic override)
  2. Environment variables (e.g. ``GITHUB_TOKEN`` or nested ``GITHUB__ORG``)
  3. ``.env`` file (env-var format)
  4. ``scan-config.toml`` (or path provided to :func:`load_settings`)
  5. Built-in defaults in this module

The GitHub token is intentionally kept *outside* the TOML config so it never
gets committed accidentally — it must be supplied via the ``GITHUB_TOKEN``
environment variable (typically through ``.env``).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

DEFAULT_CONFIG_PATH = "scan-config.toml"


class GitHubSection(BaseModel):
    org: str = "opentelekomcloud-docs"
    branch: str = "main"
    api_url: str = "https://api.github.com"


class ScannerSection(BaseModel):
    api_ref_path: str = "api-ref/source"
    excluded_segments: list[str] = Field(
        default_factory=lambda: ["out-of-date_apis"],
        description="Path segments that exclude files from processing.",
    )
    # Single source of the worker default; ScannerService requires the value,
    max_workers: int = Field(default=8, ge=1, le=64)

    @property
    def rst_source_prefix(self) -> str:
        """Path prefix for RST endpoint files."""
        return self.api_ref_path.rstrip("/") + "/"


class OutputSection(BaseModel):
    path: str = "scan-output.json"
    indent: int = 2


class LoggingSection(BaseModel):
    level: str = "INFO"


class DatabaseSection(BaseModel):
    """PostgreSQL connection settings for the panel backend.

    ``url`` must be a PostgreSQL SQLAlchemy URL (``postgresql+psycopg://``).
    Override via the ``DATABASE__URL`` environment variable.
    """

    url: str = "postgresql+psycopg://panel:panel@localhost:5432/panel"


class PanelSection(BaseModel):
    frontend_origin: str = "http://localhost:5173"


class Settings(BaseSettings):
    github_token: SecretStr | None = Field(
        default=None,
        description=(
            "GitHub personal access token. Must come from env or .env — "
            "never from the TOML config file. Required only for scanning; "
            "the panel/DB layer does not need it."
        ),
    )
    github: GitHubSection = Field(default_factory=GitHubSection)
    scanner: ScannerSection = Field(default_factory=ScannerSection)
    output: OutputSection = Field(default_factory=OutputSection)
    logging: LoggingSection = Field(default_factory=LoggingSection)
    database: DatabaseSection = Field(default_factory=DatabaseSection)
    panel: PanelSection = Field(default_factory=PanelSection)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        env_nested_delimiter="__",  # GITHUB__ORG=... overrides github.org
        toml_file=DEFAULT_CONFIG_PATH,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Order = precedence (earlier wins). env > .env > TOML > defaults.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load :class:`Settings`, optionally from a custom TOML config path.

    If ``config_path`` is ``None``, uses :data:`DEFAULT_CONFIG_PATH`
    (``scan-config.toml`` in CWD). A missing default file is tolerated —
    defaults + env are still applied. An explicitly-provided path that
    doesn't exist raises :class:`FileNotFoundError`.
    """
    if config_path is None:
        return Settings()

    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    # Subclass-with-overridden-config is the recommended pattern for changing
    # toml_file at construction time (it is a class-level option in pydantic-settings).
    class _ScopedSettings(Settings):
        model_config = SettingsConfigDict(
            **{**Settings.model_config, "toml_file": str(path)}
        )

    return _ScopedSettings()


def require_github_token(settings: Settings) -> SecretStr:
    """Return the configured GitHub token, or raise if scanning without one.

    The token is optional at the settings level so the panel/DB layer and
    migrations never depend on it. Callers that actually reach GitHub (the
    scanner composition root) enforce its presence here.
    """
    if settings.github_token is None:
        raise RuntimeError(
            "GITHUB_TOKEN is not set. Provide it via the GITHUB_TOKEN "
            "environment variable or a .env file to scan repositories."
        )
    return settings.github_token
