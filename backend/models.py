from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator


def now() -> datetime:
    return datetime.now(timezone.utc)


class State(str, Enum):
    REQUESTED = "REQUESTED"
    QUEUED = "QUEUED"
    PROVISIONING = "PROVISIONING"
    RUNNING = "RUNNING"
    RELEASING = "RELEASING"
    COMPLETED = "COMPLETED"
    RELEASED = "RELEASED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")
    tokens: dict[str, str]
    admin: str
    image: str = "alpine:latest"
    host_cpu_millis: PositiveInt = 2000
    host_memory_mib: PositiveInt = 2048
    headroom_cpu_millis: PositiveInt = 500
    headroom_memory_mib: PositiveInt = 512
    default_cpu_millis: int = Field(default=500, ge=10)
    default_memory_mib: int = Field(default=256, ge=6)
    max_sessions: PositiveInt = 20
    per_user: PositiveInt = 2
    pids: int = Field(default=32, ge=8)
    lifetime_seconds: PositiveInt = 900
    queue_seconds: PositiveInt = 300
    poll_seconds: float = Field(default=1, gt=0, le=10)
    docker_timeout_seconds: PositiveInt = 10
    terminal_origin: str = "http://127.0.0.1:8000"

    @property
    def cpu_budget(self) -> int:
        return self.host_cpu_millis - self.headroom_cpu_millis

    @property
    def memory_budget(self) -> int:
        return self.host_memory_mib - self.headroom_memory_mib

    @model_validator(mode="after")
    def validate_settings(self) -> Settings:
        if self.admin not in self.tokens.values() or not self.admin:
            raise ValueError("admin must identify a configured user")
        for token, owner in self.tokens.items():
            if not token or not owner or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in token):
                raise ValueError("tokens must be nonempty URL-safe strings mapped to nonempty identities")
        if self.default_cpu_millis > self.cpu_budget or self.default_memory_mib > self.memory_budget:
            raise ValueError("default request must fit after host headroom")
        return self

    @classmethod
    def from_env(cls) -> Settings:
        return cls.model_validate(json.loads(os.environ["OPENLABSCALE_CONFIG"]))


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cpu_millis: Optional[int] = Field(default=None, ge=10)
    memory_mib: Optional[int] = Field(default=None, ge=6)


class LifecycleEvent(BaseModel):
    state: State
    at: datetime


class Session(BaseModel):
    id: str
    owner: str
    cpu_millis: int
    memory_mib: int
    state: State = State.REQUESTED
    created_at: datetime = Field(default_factory=now)
    events: list[LifecycleEvent] = Field(default_factory=list)
    container_id: Optional[str] = None
    failure: Optional[str] = None
    cleanup_pending: bool = False
    queue_position: Optional[int] = None
    queue_seconds: Optional[float] = None
    provisioning_seconds: Optional[float] = None
