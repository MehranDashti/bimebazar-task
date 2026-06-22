from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET_KEYS = {
    "change-me-in-production",
    "change-me-in-production-use-a-long-random-string-min-32-chars",
}


class Settings(BaseSettings):
    SERVER_LISTEN_IP: str = "0.0.0.0"
    SERVER_LISTEN_PORT: int = 8000
    SERVER_WORKERS: int = 1
    PRODUCTION: bool = False

    APP_NAME: str = "MyApp"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    CORS_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    DATABASE_URL: str = "mysql+aiomysql://user:pass@localhost:3306/mydb"

    LOG_LEVEL: str = "INFO"
    SYSLOG_HOST: str = "localhost"
    SYSLOG_PORT: int = 514

    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Toggle the in-memory auth rate limiter (disable in tests/CI).
    RATE_LIMIT_ENABLED: bool = True

    SEED_ADMIN_EMAIL: str = "admin@example.com"
    SEED_ADMIN_USERNAME: str = "admin"
    SEED_ADMIN_FULLNAME: str = "System Administrator"
    SEED_ADMIN_PASSWORD: str = "Admin1234"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        if self.PRODUCTION and (
            self.SECRET_KEY in _INSECURE_SECRET_KEYS or len(self.SECRET_KEY) < 32
        ):
            raise ValueError(
                "SECRET_KEY must be changed from its default and be at least 32 "
                "characters when PRODUCTION=true. Generate one with: "
                "python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        return self


settings = Settings()
