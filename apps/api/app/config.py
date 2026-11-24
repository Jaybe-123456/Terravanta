import re
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Terravanta API"
    app_env: str = "development"
    service_mode: Literal["api", "worker"] = "api"
    database_url: str = "sqlite:///./terrava.db"
    migrations_database_url: str = ""
    cors_origins: str = "http://localhost:3000"
    # Stable public Vercel production URL. Keep preview deployments out of this allowlist.
    public_app_origin: str = "https://terravanta-five.vercel.app"
    demo_auth_secret: str = "local-demo-only-change-me"
    enable_synthetic_data: bool = False
    supabase_url: str = ""
    supabase_jwks_url: str = ""
    supabase_anon_key: str = ""
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_chat_model: str = "nvidia/nemotron-3.5-bolt-e4b"
    nvidia_parse_model: str = "nvidia/nemotron-3.5-parse"
    nvidia_parse_url: str = "https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-parse/parse"
    nvidia_parse_api_key: str = ""
    uploads_dir: str = "./data/uploads"
    evidence_storage_backend: str = "local"
    evidence_local_storage_persistent: bool = False
    evidence_s3_bucket: str = ""
    evidence_s3_region: str = "us-east-1"
    evidence_s3_endpoint_url: str = ""
    evidence_s3_access_key: str = ""
    evidence_s3_secret_key: str = ""
    evidence_max_file_bytes: int = 15_000_000
    evidence_scanner_host: str = ""
    evidence_scanner_port: int = 3310
    evidence_scanner_timeout_seconds: float = 8.0
    evidence_retention_purge_enabled: bool = False
    ai_timeout_seconds: int = 35
    workflow_poll_seconds: int = 30
    whatsapp_worker_database_url: str = ""
    whatsapp_webhook_database_url: str = ""
    whatsapp_pairing_secret: str = ""
    meta_wa_access_token: str = ""
    meta_wa_phone_number_id: str = ""
    meta_wa_business_number: str = ""
    meta_wa_app_secret: str = ""
    meta_wa_verify_token: str = ""
    meta_wa_graph_api_version: str = ""
    meta_wa_notification_template: str = ""
    meta_wa_template_language: str = "en"
    meta_wa_send_enabled: bool = False
    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")

    @field_validator("database_url", "migrations_database_url", "whatsapp_worker_database_url", "whatsapp_webhook_database_url", mode="before")
    @classmethod
    def normalize_postgres_driver(cls, value):
        # Managed PostgreSQL providers commonly expose postgresql:// URLs.
        # This project uses psycopg 3, so select its SQLAlchemy dialect explicitly.
        if isinstance(value, str):
            if value.startswith("postgres://"):
                return "postgresql+psycopg://" + value.removeprefix("postgres://")
            if value.startswith("postgresql://"):
                return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        configured = [item.strip() for item in self.cors_origins.split(",") if item.strip()]
        if self.app_env.lower() in {"production", "test"} and self.public_app_origin.strip():
            configured.append(self.public_app_origin.strip().rstrip("/"))
        return list(dict.fromkeys(configured))

    @property
    def effective_supabase_jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return ""

    @property
    def whatsapp_webhook_configured(self) -> bool:
        return bool(
            self.meta_wa_app_secret
            and self.meta_wa_verify_token
            and self.meta_wa_phone_number_id
            and (self.whatsapp_webhook_database_url or self.app_env.lower() != "production")
        )

    @property
    def whatsapp_pairing_configured(self) -> bool:
        return bool(
            self.whatsapp_webhook_configured
            and self.meta_wa_business_number
            and self.whatsapp_pairing_secret
        )

    @property
    def whatsapp_delivery_configured(self) -> bool:
        return bool(
            self.meta_wa_send_enabled
            and self.meta_wa_access_token
            and self.meta_wa_phone_number_id
            and self.meta_wa_graph_api_version
            and self.meta_wa_notification_template
        )

    @property
    def whatsapp_delivery_enabled(self) -> bool:
        return self.meta_wa_send_enabled

    @model_validator(mode="after")
    def require_production_auth_configuration(self):
        if self.app_env.lower() == "production":
            if not self.database_url.startswith("postgresql+"):
                raise ValueError("Production requires DATABASE_URL to use the restricted PostgreSQL runtime role")
            if self.service_mode == "api" and not (self.supabase_url and self.supabase_anon_key):
                raise ValueError("Production API requires Supabase Auth configuration")
            if self.service_mode == "api" and not self.migrations_database_url:
                raise ValueError("Production requires MIGRATIONS_DATABASE_URL for schema and operator tasks")
            if self.service_mode == "api" and "*" in self.allowed_origins:
                raise ValueError("Production CORS_ORIGINS must list explicit origins")
            if self.enable_synthetic_data:
                raise ValueError("Synthetic data must be disabled in production")
        return self

    @model_validator(mode="after")
    def validate_evidence_storage_configuration(self):
        if self.evidence_storage_backend not in {"local", "s3"}:
            raise ValueError("EVIDENCE_STORAGE_BACKEND must be local or s3")
        if self.evidence_storage_backend == "s3" and not self.evidence_s3_bucket:
            raise ValueError("EVIDENCE_S3_BUCKET is required when S3 evidence storage is enabled")
        if self.evidence_max_file_bytes < 1024 or self.evidence_max_file_bytes > 50_000_000:
            raise ValueError("EVIDENCE_MAX_FILE_BYTES must be between 1024 and 50000000")
        if self.evidence_scanner_port < 1 or self.evidence_scanner_port > 65535:
            raise ValueError("EVIDENCE_SCANNER_PORT must be between 1 and 65535")
        if self.evidence_scanner_timeout_seconds <= 0 or self.evidence_scanner_timeout_seconds > 60:
            raise ValueError("EVIDENCE_SCANNER_TIMEOUT_SECONDS must be greater than 0 and at most 60")
        if self.evidence_retention_purge_enabled:
            raise ValueError("Timed evidence purge is disabled until an approved retention schedule and restore drill exist")
        return self

    @model_validator(mode="after")
    def validate_whatsapp_configuration(self):
        if self.app_env.lower() == "production" and (self.meta_wa_app_secret or self.meta_wa_verify_token):
            if not self.whatsapp_webhook_database_url:
                raise ValueError("Production Meta webhook requires WHATSAPP_WEBHOOK_DATABASE_URL using the restricted webhook role")
        if self.meta_wa_send_enabled:
            missing = [name for name, value in (
                ("META_WA_ACCESS_TOKEN", self.meta_wa_access_token),
                ("META_WA_PHONE_NUMBER_ID", self.meta_wa_phone_number_id),
                ("META_WA_GRAPH_API_VERSION", self.meta_wa_graph_api_version),
                ("META_WA_NOTIFICATION_TEMPLATE", self.meta_wa_notification_template),
            ) if not value]
            if self.service_mode == "worker" and not self.whatsapp_worker_database_url:
                missing.append("WHATSAPP_WORKER_DATABASE_URL")
            if missing:
                raise ValueError("WhatsApp sending is enabled but required settings are missing: " + ", ".join(missing))
            if not re.fullmatch(r"v\d+\.\d+", self.meta_wa_graph_api_version):
                raise ValueError("META_WA_GRAPH_API_VERSION must be explicitly set, for example vXX.X")
        return self


settings = Settings()
