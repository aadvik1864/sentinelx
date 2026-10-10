import secrets
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./sentinelx.db"
    redis_url: str = ""
    jwt_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False
    api_docs_enabled: bool = False
    allowed_origins: str = "http://localhost:5173,http://localhost:8080"
    allowed_hosts: str = "localhost,127.0.0.1"
    bootstrap_admin_email: str = "admin@sentinelx.dev"
    bootstrap_admin_password: str = ""
    demo_mode: bool = False
    seed_demo: bool = False
    live_monitoring: bool = False
    llm_provider: Literal["auto", "offline", "openai", "ollama"] = "auto"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = Field(default=180, ge=10, le=180)
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:1.7b"
    abuseipdb_api_key: str = ""

    @property
    def ai_provider(self) -> str:
        if self.llm_provider == "auto":
            return "openai" if self.llm_api_key else "offline"
        return self.llm_provider

    @property
    def origins(self) -> list[str]:
        return [value.strip() for value in self.allowed_origins.split(",") if value.strip()]

    @property
    def hosts(self) -> list[str]:
        return [value.strip() for value in self.allowed_hosts.split(",") if value.strip()]

    @model_validator(mode="after")
    def check_security(self):
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("ENVIRONMENT must be development, test, or production")
        if self.live_monitoring and (self.demo_mode or self.seed_demo):
            raise ValueError("Live monitoring requires DEMO_MODE=false and SEED_DEMO=false")
        if not self.hosts or any("*" in host for host in self.hosts):
            raise ValueError(
                "ALLOWED_HOSTS must explicitly list trusted hostnames, without wildcards"
            )
        if self.llm_provider == "openai" and not self.llm_api_key:
            raise ValueError("LLM_PROVIDER=openai requires LLM_API_KEY")
        if self.llm_provider == "ollama":
            url = urlsplit(self.ollama_base_url)
            if (
                url.scheme != "http"
                or url.hostname not in {"ollama", "localhost", "127.0.0.1", "::1"}
                or url.username is not None
                or url.password is not None
                or url.path not in {"", "/"}
                or url.query
                or url.fragment
            ):
                raise ValueError("Ollama must use the private Compose service or loopback HTTP")
            if not self.ollama_model.strip() or "cloud" in self.ollama_model.lower():
                raise ValueError("Ollama requires a downloaded local model, not a cloud model")
        if self.environment == "production":
            if self.api_docs_enabled:
                raise ValueError("API documentation must be disabled in production")
            if len(self.jwt_secret) < 32 or not self.cookie_secure:
                raise ValueError(
                    "Production requires a 32+ character JWT_SECRET and secure cookies"
                )
            if not self.redis_url or not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL and Redis")
            if self.demo_mode or self.seed_demo:
                raise ValueError("Demo mode and demo seeding must be disabled in production")
            if not self.origins:
                raise ValueError("Production requires explicit HTTPS origins")
            for origin in self.origins:
                url = urlsplit(origin)
                if (
                    url.scheme != "https"
                    or url.hostname not in self.hosts
                    or url.username is not None
                    or url.password is not None
                    or url.path
                    or url.query
                    or url.fragment
                    or (url.port is not None and not 1 <= url.port <= 65535)
                ):
                    raise ValueError(
                        "Production origins must be exact HTTPS origins with explicitly allowed hostnames"
                    )
        if not self.jwt_secret:
            # Ephemeral development secret: restarting intentionally invalidates existing access tokens.
            self.jwt_secret = secrets.token_urlsafe(48)
        elif len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
