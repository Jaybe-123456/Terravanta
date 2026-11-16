from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Terravanta API"
    app_env: str = "development"
    database_url: str = "sqlite:///./terrava.db"
    cors_origins: str = "http://localhost:3000"
    # Stable public Vercel production URL. Keep preview deployments out of this allowlist.
    public_app_origin: str = "https://terravanta-five.vercel.app"
    demo_auth_secret: str = "local-demo-only-change-me"
    enable_synthetic_data: bool = False
    supabase_url: str = ""
    supabase_jwks_url: str = ""
    supabase_anon_key: str = ""
    temp_access_auth_enabled: bool = False
    resend_api_key: str = ""
    access_code_from_email: str = ""
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_chat_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    nvidia_parse_model: str = "nvidia/nemotron-3.5-parse"
    nvidia_parse_url: str = ""
    nvidia_parse_api_key: str = ""
    uploads_dir: str = "./data/uploads"
    ai_timeout_seconds: int = 35
    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")

    @field_validator("database_url", mode="before")
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

    @model_validator(mode="after")
    def require_production_auth_configuration(self):
        if self.app_env.lower() == "production":
            if len(self.demo_auth_secret) < 32 or self.demo_auth_secret == "local-demo-only-change-me":
                raise ValueError("Production requires a unique DEMO_AUTH_SECRET of at least 32 characters")
            has_supabase = bool(self.supabase_url and self.supabase_anon_key)
            if not has_supabase and not self.temp_access_auth_enabled:
                raise ValueError("Production requires Supabase Auth or explicitly enabled temporary access-code auth")
            if "*" in self.allowed_origins:
                raise ValueError("Production CORS_ORIGINS must list explicit origins")
            if self.enable_synthetic_data:
                raise ValueError("Synthetic data must be disabled in production")
        return self


settings = Settings()
