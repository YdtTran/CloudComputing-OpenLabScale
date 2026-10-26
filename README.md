# OpenLab-Scale (OLS)

[![License Management](https://img.shields.io/badge/License%20Seats-100%20Atomic-blue)](./services/license-manager)
[![eBPF Fallback](https://img.shields.io/badge/Telemetry-eBPF%20%7C%20Cgroup%20v2-green)](./services/ebpf-agent)
[![Docker Compose](https://img.shields.io/badge/Orchestration-Docker%20Compose-blueviolet)](./docker-compose.yml)

OpenLab-Scale is a cloud-native platform providing atomic, high-concurrency license management (100 seats) paired with host kernel observability via eBPF and automated cgroup v2 fallback.

---

## Architecture Overview

```
                      +-----------------------------+
                      |       Mock Workload         |
                      | (profile: workload, Docker) |
                      +--------------+--------------+
                                     |
                                     | HTTP REST
                                     v
+------------------+         +-------------------------------+
|    ebpf-agent    | <-----> |        license-manager        |
|  (eBPF / Cgroup) |         | (FastAPI, 100 Seats, Hot-Rel) |
+------------------+         +---------------+---------------+
         |                                   |
         | Telemetry                         | Redis State
         v                                   v
+------------------+         +-------------------------------+
| Host / Kernel /  |         |             Redis             |
| Docker & Cgroups |         |     (7.2 Alpine, AOF Store)   |
+------------------+         +-------------------------------+
```

### Services Breakdown

1. **`redis`**:
   - Redis 7.2 Alpine with persistent Append-Only File (`AOF`) enabled.
   - Built-in container healthcheck via `redis-cli ping`.
   - Stores atomic seat state, expiration sorted sets, and workload-to-lease mappings.

2. **`license-manager`**:
   - Python 3.11-slim FastAPI service.
   - Volume mounted at `./services/license-manager/src:/app/src` for instant hot-reloading (`--reload`).
   - Atomic seat allocation powered by Lua scripting (guarantees `active_seats <= 100`).
   - TTL-based automatic lease reclamation and heartbeat renewal.
   - Healthcheck integration waiting for Redis readiness before start.

3. **`ebpf-agent`**:
   - Python 3.11 telemetry agent.
   - Runs with host PID/cgroup namespace and elevated capabilities (`BPF`, `PERFMON`, `SYS_ADMIN`).
   - Volume mounts for `/sys/kernel/btf`, `/sys/kernel/debug`, `/sys/fs/cgroup`, and `/var/run/docker.sock`.
   - **Graceful Fallback**: Automatically checks for BTF (`/sys/kernel/btf/vmlinux`). If absent or unsupported, safely degrades to cgroup v2 and procfs resource inspection.

4. **`mock-workload`**:
   - Synthetic workload runner placed under the Docker Compose profile `workload`.
   - Exercises the complete lifecycle: request seat -> periodic heartbeat -> graceful release on exit.

---

## Directory Structure

```text
.
├── .env.example                     # Environment template
├── docker-compose.yml               # Multi-service composition
├── README.md                        # Project documentation
├── scripts/
│   └── smoke_test.sh                # Reproducible automated verification script
├── services/
│   ├── license-manager/             # FastAPI 100-seat License Manager
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── config.py
│   │       └── main.py
│   ├── ebpf-agent/                  # Host Observability Agent (eBPF + Fallback)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       └── agent.py
│   └── mock-workload/               # Synthetic Workload Generator
│       ├── Dockerfile
│       └── src/
│           └── workload.py
└── logs/                            # Service and agent log output
```

---

## Prerequisites

- **Docker & Docker Compose**: Docker 24.0+ and Docker Compose v2.
- **Host Kernel (for native eBPF)**: Linux Kernel >= 5.8 with BTF (`CONFIG_DEBUG_INFO_BTF=y` at `/sys/kernel/btf/vmlinux`).
- **Fallback Compatibility**: Windows, macOS, and Linux kernels without BTF will run seamlessly via the automatic cgroup v2 / procfs fallback.

---

## Quickstart

### 1. One-Command Setup

Initialize the environment and launch the core stack (`redis`, `license-manager`, `ebpf-agent`):

```bash
# 1. Initialize environment file
cp .env.example .env

# 2. Build and start containers in detached mode
docker compose up -d --build redis license-manager ebpf-agent
```

### 2. Verify Services

Check running container status and logs:

```bash
# Check container status
docker compose ps

# View license-manager logs
docker compose logs -f license-manager

# View ebpf-agent logs (inspects BTF or fallback status)
docker compose logs -f ebpf-agent
```

---

## Automated Smoke Testing

A reproducible automated test script is provided in `scripts/smoke_test.sh`. It performs:
1. Host kernel, BTF presence, and cgroups v2 detection.
2. Environment verification (copies `.env.example` to `.env` if missing).
3. Service startup via `docker compose up -d --build redis license-manager ebpf-agent`.
4. Healthcheck polling on `GET /health` with retry/timeout logic.
5. End-to-end seat lifecycle tests: Request Seat -> Verify `active_seats <= 100` -> Release Seat.
6. Clean automated teardown.

To run the smoke test:

```bash
chmod +x scripts/smoke_test.sh
./scripts/smoke_test.sh
```

---

## Launching the Mock Workload

The mock workload is isolated behind the `workload` compose profile so it does not interfere with standard operations:

```bash
# Start a synthetic workload instance
docker compose --profile workload up -d mock-workload

# Follow workload logs
docker compose logs -f mock-workload
```

---

## API Reference

### 1. Service Health
- **Endpoint**: `GET /health`
- **Response**:
  ```json
  {
    "status": "healthy",
    "redis": "connected",
    "active_seats": 0,
    "max_seats": 100,
    "ebpf_mode": "auto",
    "version": "1.0.0"
  }
  ```

### 2. Seat Pool Status
- **Endpoint**: `GET /api/v1/licenses/status`
- **Response**:
  ```json
  {
    "total_seats": 100,
    "active_seats": 0,
    "available_seats": 100,
    "allocation_policy": "baseline",
    "ebpf_mode": "auto",
    "leases": []
  }
  ```

### 3. Request Seat Lease
- **Endpoint**: `POST /api/v1/licenses/request`
- **Body**:
  ```json
  {
    "workload_id": "job-worker-01",
    "ttl_seconds": 60,
    "metadata": { "job_type": "batch" }
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "action": "allocated",
    "lease_id": "4b6efcb5-2a91-4c69-8dcf-3c72bdfb7381",
    "workload_id": "job-worker-01",
    "allocated_at": 1729931000.0,
    "expires_at": 1729931060.0,
    "active_seats": 1,
    "remaining_seats": 99
  }
  ```

### 4. Release Seat Lease
- **Endpoint**: `POST /api/v1/licenses/release`
- **Body**:
  ```json
  {
    "lease_id": "4b6efcb5-2a91-4c69-8dcf-3c72bdfb7381",
    "workload_id": "job-worker-01"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "released_lease_id": "4b6efcb5-2a91-4c69-8dcf-3c72bdfb7381",
    "active_seats": 0,
    "remaining_seats": 100
  }
  ```

### 5. Heartbeat Renewal
- **Endpoint**: `POST /api/v1/licenses/heartbeat`
- **Body**:
  ```json
  {
    "lease_id": "4b6efcb5-2a91-4c69-8dcf-3c72bdfb7381",
    "extend_seconds": 60
  }
  ```

---

## eBPF vs. Cgroup Fallback Mode

The telemetry agent is built to be resilient across heterogeneous environments:

| Feature / Mode | eBPF Tracing Mode | Cgroup v2 Fallback Mode |
| :--- | :--- | :--- |
| **Trigger** | `/sys/kernel/btf/vmlinux` present & `EBPF_MODE=auto` | BTF missing OR `EBPF_MODE=fallback` |
| **Requirements** | Host Linux >= 5.8, BTF enabled | Standard Linux cgroups v2 / procfs |
| **Process Inspection** | Kernel socket & probe tracing | `/sys/fs/cgroup` & `/proc` hierarchy |
| **Container Metrics** | Socket-level network + process events | CPU stat, memory usage, load averages |
| **Environment Suitability** | Production Linux servers | Local workstations, CI containers, Dev |
