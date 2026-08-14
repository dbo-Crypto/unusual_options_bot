from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_mode: str = "replay"  # replay | live
    poll_interval_seconds: int = 240
    max_scan_underlyings: int = 120

    postgres_user: str = "uoa"
    postgres_password: str = "uoa"
    postgres_db: str = "uoa"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    fixtures_dir: str = "/app/fixtures"

    feed_min_score: float = 55.0
    unusual_min_score: float = 70.0
    alert_min_score: float = 80.0

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
