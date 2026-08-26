from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_prefix="OFFICE_COOK_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "OfficeCookAssistant API"
    app_version: str = "dev"
    build_date: str = "unknown"
    environment: str = "development"
    database_url: str | None = None
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "officecook"
    database_user: str = "officecook"
    database_password: SecretStr = SecretStr("officecook")
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    sql_echo: bool = False
    session_cookie_secure: bool = False
    session_ttl_hours: int = Field(default=12, ge=1, le=24)

    @field_validator("allowed_hosts", "cors_origins")
    @classmethod
    def reject_wildcards(cls, values: list[str]) -> list[str]:
        if not values or any(value.strip() == "*" for value in values):
            raise ValueError("an explicit non-empty allowlist is required")
        return values

    @field_validator("database_url")
    @classmethod
    def require_async_postgresql(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = make_url(value)
        if parsed.drivername != "postgresql+asyncpg":
            raise ValueError("database_url must use postgresql+asyncpg")
        return value

    def build_database_url(self) -> URL:
        """Return a structured URL so component credentials are escaped by SQLAlchemy."""
        if self.database_url is not None:
            return make_url(self.database_url)
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )

    @model_validator(mode="after")
    def require_secure_production_cookies(self) -> "Settings":
        if self.environment.lower() == "production" and not self.session_cookie_secure:
            raise ValueError("production requires secure session cookies")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
