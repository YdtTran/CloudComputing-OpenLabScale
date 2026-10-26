"""OpenLab-Scale License Manager Service.

Provides an atomic 100-seat license allocation system backed by Redis with
TTL lease expiration, heartbeat maintenance, and observability.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import fakeredis
import redis
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from src.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("license-manager")

# Redis Key Constants
KEY_LEASES = "ols:licenses:leases"                # Hash: lease_id -> JSON string
KEY_EXPIRATIONS = "ols:licenses:expirations"      # ZSet: lease_id -> expiration_timestamp
KEY_WORKLOAD_MAP = "ols:licenses:workload_map"    # Hash: workload_id -> lease_id

# Redis Lua Script for Atomic Lease Allocation
LUA_REQUEST_LEASE = """
local leases_key = KEYS[1]
local expirations_key = KEYS[2]
local workload_map_key = KEYS[3]

local now = tonumber(ARGV[1])
local max_seats = tonumber(ARGV[2])
local lease_id = ARGV[3]
local workload_id = ARGV[4]
local expires_at = tonumber(ARGV[5])
local lease_data = ARGV[6]

-- Step 1: Cleanup expired leases
local expired_ids = redis.call('ZRANGEBYSCORE', expirations_key, '-inf', now)
for _, exp_id in ipairs(expired_ids) do
    local old_data = redis.call('HGET', leases_key, exp_id)
    if old_data then
        -- Decode or find workload_id to remove mapping
        redis.call('HDEL', leases_key, exp_id)
    end
end
if #expired_ids > 0 then
    redis.call('ZREMRANGEBYSCORE', expirations_key, '-inf', now)
end

-- Step 2: Check if workload already holds a valid lease (idempotent renew)
local existing_lease_id = redis.call('HGET', workload_map_key, workload_id)
if existing_lease_id and redis.call('HEXISTS', leases_key, existing_lease_id) == 1 then
    redis.call('ZADD', expirations_key, expires_at, existing_lease_id)
    redis.call('HSET', leases_key, existing_lease_id, lease_data)
    local active_count = redis.call('ZCARD', expirations_key)
    return {1, existing_lease_id, tostring(active_count), "renewed"}
end

-- Step 3: Check seat capacity limit
local current_active = redis.call('ZCARD', expirations_key)
if current_active >= max_seats then
    return {0, "capacity_exceeded", tostring(current_active)}
end

-- Step 4: Atomically allocate new seat
redis.call('HSET', leases_key, lease_id, lease_data)
redis.call('ZADD', expirations_key, expires_at, lease_id)
redis.call('HSET', workload_map_key, workload_id, lease_id)
local new_active = redis.call('ZCARD', expirations_key)
return {1, lease_id, tostring(new_active), "allocated"}
"""

# Redis Lua Script for Atomic Lease Release
LUA_RELEASE_LEASE = """
local leases_key = KEYS[1]
local expirations_key = KEYS[2]
local workload_map_key = KEYS[3]

local target_lease_id = ARGV[1]
local target_workload_id = ARGV[2]

-- Resolve target lease_id if workload_id provided
if (not target_lease_id or target_lease_id == "") and target_workload_id ~= "" then
    target_lease_id = redis.call('HGET', workload_map_key, target_workload_id)
end

if not target_lease_id or redis.call('HEXISTS', leases_key, target_lease_id) == 0 then
    local current_active = redis.call('ZCARD', expirations_key)
    return {0, "not_found", tostring(current_active)}
end

-- Fetch workload_id from lease if needed to clean up mapping
local raw_lease = redis.call('HGET', leases_key, target_lease_id)
redis.call('HDEL', leases_key, target_lease_id)
redis.call('ZREM', expirations_key, target_lease_id)

if target_workload_id ~= "" then
    redis.call('HDEL', workload_map_key, target_workload_id)
end

local remaining_active = redis.call('ZCARD', expirations_key)
return {1, target_lease_id, tostring(remaining_active), "released"}
"""


class RedisState:
    client: Optional[redis.Redis] = None
    is_in_memory: bool = False
    req_script = None
    rel_script = None


state = RedisState()


def init_redis_connection() -> redis.Redis:
    """Connect to Redis with fallback to in-memory FakeRedis."""
    # If dev mode is enabled and Redis host is unresolvable or fallback allowed
    if os.getenv("OLS_DEV_MODE") == "1" and settings.REDIS_HOST == "redis":
        logger.info("OLS_DEV_MODE active: using in-memory FakeRedis state store.")
        state.is_in_memory = True
        return fakeredis.FakeRedis(decode_responses=True)

    try:
        import socket
        socket.setdefaulttimeout(1.5)
        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
        )
        client.ping()
        state.is_in_memory = False
        logger.info("Successfully connected to Redis at %s:%d", settings.REDIS_HOST, settings.REDIS_PORT)
        return client
    except Exception as exc:
        if settings.REDIS_FALLBACK_MEMORY:
            logger.warning("Could not connect to Redis (%s). Using in-memory fallback.", exc)
            state.is_in_memory = True
            return fakeredis.FakeRedis(decode_responses=True)
        raise exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    state.client = init_redis_connection()
    state.req_script = state.client.register_script(LUA_REQUEST_LEASE)
    state.rel_script = state.client.register_script(LUA_RELEASE_LEASE)
    logger.info(
        "License Manager initialized (MAX_SEATS=%d, LEASE_TTL=%ds, POLICY=%s, IN_MEMORY=%s)",
        settings.MAX_SEATS,
        settings.LEASE_TTL_SEC,
        settings.ALLOCATION_POLICY,
        state.is_in_memory,
    )
    yield
    if state.client:
        try:
            state.client.close()
        except Exception:
            pass
    logger.info("License Manager shut down.")


app = FastAPI(
    title="OpenLab-Scale License Manager",
    description="Atomic 100-seat license management service with eBPF fallback support",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Pydantic Request / Response Models ---

class LicenseRequest(BaseModel):
    workload_id: Optional[str] = Field(default=None, description="Identifier of the requesting workload")
    ttl_seconds: Optional[int] = Field(default=None, description="Requested lease duration in seconds")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary workload metadata")


class LicenseReleaseRequest(BaseModel):
    lease_id: Optional[str] = Field(default=None, description="Lease ID to release")
    workload_id: Optional[str] = Field(default=None, description="Workload ID whose lease should be released")


class HeartbeatRequest(BaseModel):
    lease_id: str = Field(description="Active lease ID")
    workload_id: Optional[str] = Field(default=None, description="Workload identifier")
    extend_seconds: Optional[int] = Field(default=None, description="Duration to extend lease")


class LicenseResponse(BaseModel):
    success: bool
    action: str
    lease_id: str
    workload_id: str
    allocated_at: float
    expires_at: float
    active_seats: int
    remaining_seats: int


class LicenseStatusResponse(BaseModel):
    total_seats: int
    active_seats: int
    available_seats: int
    allocation_policy: str
    ebpf_mode: str
    leases: List[Dict[str, Any]]


class HealthResponse(BaseModel):
    status: str
    redis: str
    active_seats: int
    max_seats: int
    ebpf_mode: str
    version: str


# --- Helper Functions ---

def prune_expired_leases() -> int:
    """Prunes expired leases from Redis and returns current active count."""
    now = time.time()
    expired = state.client.zrangebyscore(KEY_EXPIRATIONS, "-inf", now)
    if expired:
        pipe = state.client.pipeline()
        for lid in expired:
            pipe.hdel(KEY_LEASES, lid)
        pipe.zremrangebyscore(KEY_EXPIRATIONS, "-inf", now)
        pipe.execute()
    return state.client.zcard(KEY_EXPIRATIONS)


def execute_request_lease(workload_id: str, ttl: int, metadata: Dict[str, Any]):
    """Atomically requests or renews a lease across Redis or in-memory fallback."""
    now = time.time()
    expires_at = now + ttl
    new_lease_id = str(uuid.uuid4())
    lease_payload = {
        "lease_id": new_lease_id,
        "workload_id": workload_id,
        "allocated_at": now,
        "expires_at": expires_at,
        "ttl_seconds": ttl,
        "metadata": metadata or {},
    }

    if not state.is_in_memory and state.req_script:
        try:
            res = state.req_script(
                keys=[KEY_LEASES, KEY_EXPIRATIONS, KEY_WORKLOAD_MAP],
                args=[now, settings.MAX_SEATS, new_lease_id, workload_id, expires_at, json.dumps(lease_payload)],
            )
            return int(res[0]), str(res[1]), int(res[2]), str(res[3]) if len(res) > 3 else "allocated", expires_at, now
        except Exception as script_err:
            logger.warning("Lua script execution failed (%s), using atomic pipeline fallback.", script_err)

    # Atomic pipeline fallback
    prune_expired_leases()

    # Idempotent renewal if workload already holds lease
    existing_lease_id = state.client.hget(KEY_WORKLOAD_MAP, workload_id)
    if existing_lease_id and state.client.hexists(KEY_LEASES, existing_lease_id):
        state.client.zadd(KEY_EXPIRATIONS, {existing_lease_id: expires_at})
        state.client.hset(KEY_LEASES, existing_lease_id, json.dumps(lease_payload))
        active_count = state.client.zcard(KEY_EXPIRATIONS)
        return 1, existing_lease_id, active_count, "renewed", expires_at, now

    # Capacity check
    active_count = state.client.zcard(KEY_EXPIRATIONS)
    if active_count >= settings.MAX_SEATS:
        return 0, "capacity_exceeded", active_count, "capacity_exceeded", expires_at, now

    # Allocate new seat
    pipe = state.client.pipeline()
    pipe.hset(KEY_LEASES, new_lease_id, json.dumps(lease_payload))
    pipe.zadd(KEY_EXPIRATIONS, {new_lease_id: expires_at})
    pipe.hset(KEY_WORKLOAD_MAP, workload_id, new_lease_id)
    pipe.execute()
    new_active = state.client.zcard(KEY_EXPIRATIONS)
    return 1, new_lease_id, new_active, "allocated", expires_at, now


def execute_release_lease(lease_id: str, workload_id: str):
    """Atomically releases a lease across Redis or in-memory fallback."""
    if not state.is_in_memory and state.rel_script:
        try:
            res = state.rel_script(
                keys=[KEY_LEASES, KEY_EXPIRATIONS, KEY_WORKLOAD_MAP],
                args=[lease_id, workload_id],
            )
            return int(res[0]), str(res[1]), int(res[2])
        except Exception as script_err:
            logger.warning("Lua release script failed (%s), using atomic pipeline fallback.", script_err)

    # Fallback release
    if not lease_id and workload_id:
        lease_id = state.client.hget(KEY_WORKLOAD_MAP, workload_id) or ""

    if not lease_id or not state.client.hexists(KEY_LEASES, lease_id):
        remaining = state.client.zcard(KEY_EXPIRATIONS)
        return 0, lease_id or "not_found", remaining

    pipe = state.client.pipeline()
    pipe.hdel(KEY_LEASES, lease_id)
    pipe.zrem(KEY_EXPIRATIONS, lease_id)
    if workload_id:
        pipe.hdel(KEY_WORKLOAD_MAP, workload_id)
    pipe.execute()
    remaining = state.client.zcard(KEY_EXPIRATIONS)
    return 1, lease_id, remaining


# --- API Routes ---

@app.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Healthcheck endpoint verifying Redis responsiveness and service state."""
    try:
        if state.client is None:
            raise HTTPException(status_code=503, detail="Service initializing")
        state.client.ping()
        active_seats = prune_expired_leases()
        redis_status = "in-memory-fallback" if state.is_in_memory else "connected"
        return HealthResponse(
            status="healthy",
            redis=redis_status,
            active_seats=active_seats,
            max_seats=settings.MAX_SEATS,
            ebpf_mode=settings.EBPF_MODE,
            version="1.0.0",
        )
    except Exception as exc:
        logger.error("Healthcheck failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Healthcheck failed: {str(exc)}",
        )


@app.get("/api/v1/licenses/status", response_model=LicenseStatusResponse)
def get_status() -> LicenseStatusResponse:
    """Returns real-time seat allocation status and list of active leases."""
    active_seats = prune_expired_leases()
    leases_raw = state.client.hgetall(KEY_LEASES)
    leases_list: List[Dict[str, Any]] = []

    for lid, raw_json in leases_raw.items():
        try:
            leases_list.append(json.loads(raw_json))
        except Exception:
            leases_list.append({"lease_id": lid, "raw": raw_json})

    return LicenseStatusResponse(
        total_seats=settings.MAX_SEATS,
        active_seats=active_seats,
        available_seats=max(0, settings.MAX_SEATS - active_seats),
        allocation_policy=settings.ALLOCATION_POLICY,
        ebpf_mode=settings.EBPF_MODE,
        leases=leases_list,
    )


@app.post("/api/v1/licenses/request")
def request_license(req: LicenseRequest):
    """Atomically requests a license seat lease for a workload."""
    workload_id = req.workload_id or f"workload-{uuid.uuid4().hex[:8]}"
    ttl = req.ttl_seconds if req.ttl_seconds and req.ttl_seconds > 0 else settings.LEASE_TTL_SEC

    success_flag, returned_lease_id, active_count, action, expires_at, now = execute_request_lease(
        workload_id, ttl, req.metadata or {}
    )

    if success_flag == 1:
        logger.info("Seat %s for workload=%s lease_id=%s (active=%d/%d)", action, workload_id, returned_lease_id, active_count, settings.MAX_SEATS)
        return {
            "success": True,
            "action": action,
            "lease_id": returned_lease_id,
            "workload_id": workload_id,
            "allocated_at": now,
            "expires_at": expires_at,
            "active_seats": active_count,
            "remaining_seats": max(0, settings.MAX_SEATS - active_count),
        }
    else:
        logger.warning("License request rejected: capacity exceeded (%d/%d)", active_count, settings.MAX_SEATS)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "success": False,
                "error": "capacity_exceeded",
                "message": f"License seat capacity of {settings.MAX_SEATS} seats has been reached",
                "active_seats": active_count,
                "max_seats": settings.MAX_SEATS,
            },
        )


@app.post("/api/v1/licenses/release")
def release_license(req: LicenseReleaseRequest):
    """Atomically releases a previously acquired seat lease."""
    lease_id = req.lease_id or ""
    workload_id = req.workload_id or ""

    if not lease_id and not workload_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either lease_id or workload_id must be provided to release a license.",
        )

    success_flag, released_id, remaining_active = execute_release_lease(lease_id, workload_id)

    if success_flag == 1:
        logger.info("Released seat lease_id=%s (remaining active=%d/%d)", released_id, remaining_active, settings.MAX_SEATS)
        return {
            "success": True,
            "released_lease_id": released_id,
            "active_seats": remaining_active,
            "remaining_seats": max(0, settings.MAX_SEATS - remaining_active),
        }
    else:
        logger.warning("Release request: lease not found (lease_id=%s, workload_id=%s)", lease_id, workload_id)
        return {
            "success": False,
            "message": "Lease not found or already expired",
            "active_seats": remaining_active,
            "remaining_seats": max(0, settings.MAX_SEATS - remaining_active),
        }


@app.post("/api/v1/licenses/heartbeat")
def heartbeat_license(req: HeartbeatRequest):
    """Extends the lease expiration for an active workload."""
    now = time.time()
    extend_sec = req.extend_seconds or settings.LEASE_TTL_SEC
    expires_at = now + extend_sec

    # Check if lease exists
    raw = state.client.hget(KEY_LEASES, req.lease_id)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease ID not found or already expired",
        )

    try:
        data = json.loads(raw)
        data["expires_at"] = expires_at
        state.client.hset(KEY_LEASES, req.lease_id, json.dumps(data))
        state.client.zadd(KEY_EXPIRATIONS, {req.lease_id: expires_at})
        return {
            "success": True,
            "lease_id": req.lease_id,
            "expires_at": expires_at,
            "heartbeat_interval_sec": settings.HEARTBEAT_INTERVAL_SEC,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
