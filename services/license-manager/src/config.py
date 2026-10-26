"""Configuration module for OpenLab-Scale License Manager."""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    MAX_SEATS: int = Field(default=100, description="Total maximum license seats available")
    LEASE_TTL_SEC: int = Field(default=60, description="Lease time-to-live in seconds")
    HEARTBEAT_INTERVAL_SEC: int = Field(default=15, description="Expected heartbeat interval")
    EBPF_MODE: str = Field(default="auto", description="eBPF mode: auto | enabled | fallback")
    ALLOCATION_POLICY: str = Field(default="baseline", description="Allocation policy: baseline | priority")
    REDIS_HOST: str = Field(default="redis", description="Redis host")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_DB: int = Field(default=0, description="Redis database index")
    REDIS_PASSWORD: str = Field(default="", description="Redis password")
    LICENSE_MANAGER_PORT: int = Field(default=8000, description="License manager port")
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    REDIS_FALLBACK_MEMORY: bool = Field(default=True, description="Allow fallback to in-memory redis if redis unreachable")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


settings = Settings()
