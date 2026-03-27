from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Storage
    storage_root: str = "/storage"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "info"

    # Workers
    cpu_worker_concurrency: int = 2
    gpu_worker_concurrency: int = 1

    # WhisperX (Day 5-6)
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"


settings = Settings()
