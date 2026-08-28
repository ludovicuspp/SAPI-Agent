"""Carga de configuración desde variables de entorno y `.env`.

Usa pydantic-settings para validación estricta. Una sola instancia cacheada.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configuración tipada del proyecto.

    Las variables se leen del entorno (o `.env`). Si falta algo crítico,
    pydantic-settings eleva error explícito al instanciar.
    """

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    sapi_db_path: Path = Field(default=REPO_ROOT / "data" / "sapi.db")
    data_dir: Path = Field(default=REPO_ROOT / "data")
    uploads_dir: Path = Field(default=REPO_ROOT / "data" / "uploads")

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: str = "http://localhost:5173"

    jwt_secret: str = "change-me-in-production"
    jwt_expires_min: int = 480

    match_threshold: int = 85
    fuzzy_threshold: int = 80
    phonetic_threshold: float = 0.75

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "SAPI-Agent <noreply@sapi-agent.local>"
    notify_cooldown_hours: int = 24
    sapi_alert_emails: str = ""

    max_upload_mb: int = 300

    hermes_api_url: str = "http://localhost:8000"
    service_token_hermes: str = ""

    admin_email: str = ""
    admin_password: str = ""

    @field_validator("jwt_secret")
    @classmethod
    def _warn_default_secret(cls, v: str) -> str:
        if v == "change-me-in-production":
            import warnings

            warnings.warn(
                "JWT_SECRET usa el valor por defecto; cámbialo en producción.",
                stacklevel=2,
            )
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def alert_emails_list(self) -> list[str]:
        return [e.strip() for e in self.sapi_alert_emails.split(",") if e.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la instancia única de Settings."""
    return Settings()
