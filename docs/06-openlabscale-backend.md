# OpenLabScale Single-Host Workspace Demo & Deployment Guide

OpenLabScale provisions real, short-lived Linux container workspaces on a single Docker host with a resource-aware FIFO admission queue, an ownership-checked browser terminal (`/#student`), and a live operational telemetry dashboard (`/#admin`). The offline `simulation/` and kernel `measured/` + `collector/` pipelines continue to operate independently.

---

## 1. Local Linux Docker Setup & Operation

### Prerequisites

- **OS & Kernel**: Linux with **cgroup v2** (`/sys/fs/cgroup/cgroup.controllers`) and readable `/proc/stat` and `/proc/meminfo` (Ubuntu 22.04/24.04 LTS, Debian 12+, or WSL2 with Docker Engine).
- **Docker Engine**: Running local daemon accessible via `unix:///var/run/docker.sock` with CPU CFS quota/period, memory, swap, and PID cgroup limits enabled.
- **Runtime**: Python `3.10+` (`venv` + `pip`) and Node.js `20+` (only needed when rebuilding `frontend/dist` or running the Vite development server; prebuilt static assets are already included in `frontend/dist/`).
- **Operator Privilege Warning**: Access to `/var/run/docker.sock` is root-equivalent on the host. Run the backend under a dedicated operator account on a controlled host and never expose the Docker socket or unauthenticated ports to untrusted networks.

Verify host prerequisites before starting:

```sh
docker info --format 'OS={{.OSType}} Cgroup={{.CgroupVersion}} CPUs={{.NCPU}} MemBytes={{.MemTotal}}'
```

### Image Preparation & Installation

Preload a trusted Linux image that provides `/bin/sh` and `/bin/sleep` and declares **no Docker volumes** (`Engine.check_runtime()` rejects images with declared volumes):

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements-test.txt

# Build static React/Vite frontend bundle (served automatically at http://127.0.0.1:8000/)
cd frontend
npm ci
npm run build
cd ..
docker pull alpine:latest
docker image inspect alpine:latest --format 'ID={{.Id}} Volumes={{json .Config.Volumes}}'
```

### Starting Backend & Frontend Locally

Generate random demo bearer tokens (or use the classroom demo tokens `token-alice`, `token-bob`, `token-admin` wired into the UI selector) and bind Uvicorn strictly to loopback (`127.0.0.1:8000`) with a **single worker** (`--workers 1`) so the in-memory FIFO ledger has a single authoritative owner:

```sh
export STUDENT_TOKEN="token-alice"
export PEER_TOKEN="token-bob"
export ADMIN_TOKEN="token-admin"
export OPENLABSCALE_CONFIG=$(python - <<'PY'
import json
import os

print(json.dumps({
    "deployment": "campus-demo",
    "image": "alpine:latest",
    "tokens": {
        os.environ["STUDENT_TOKEN"]: "alice",
        os.environ["PEER_TOKEN"]: "bob",
        os.environ["ADMIN_TOKEN"]: "admin",
    },
    "admin": "admin",
    "host_cpu_millis": 2000,
    "headroom_cpu_millis": 500,
    "host_memory_mib": 2048,
    "headroom_memory_mib": 512,
    "default_cpu_millis": 500,
    "default_memory_mib": 256,
    "max_sessions": 2,
    "per_user": 2,
    "terminal_origin": "http://127.0.0.1:8000",
}))
PY
)
uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

#### Serving Modes

1. **Single-Port Unified Mode (Recommended for Local Demos & EC2)**:
   When `frontend/dist/index.html` is present, `backend/api.py` automatically serves the compiled React application at `/` alongside the REST and WebSocket endpoints on `http://127.0.0.1:8000`:
   - **Student Portal**: `http://127.0.0.1:8000/#student`
   - **Admin Dashboard**: `http://127.0.0.1:8000/#admin`
   - **Health Check**: `http://127.0.0.1:8000/health`

2. **Two-Process Vite Development Mode (Optional)**:
   For frontend hot-reload on `http://127.0.0.1:5173` (which proxies `/sessions`, `/stats`, `/health`, and WebSocket `/sessions/{id}/terminal` to `VITE_API_TARGET`, defaulting to `http://127.0.0.1:8000` with `rewriteWsOrigin: true`):
   ```sh
   cd frontend
   npm run dev
   ```

3. **Containerized Backend Mode (Docker Desktop / WSL2 or Linux)**:
   ```sh
   docker build -f backend.Dockerfile -t openlabscale-backend:local .
   docker run --rm --name openlabscale-demo \
     -p 127.0.0.1:8000:8000 \
     -v /var/run/docker.sock:/var/run/docker.sock \
     --env-file openlabscale.env \
     openlabscale-backend:local
   ```

### Graceful Shutdown & Local Cleanup

1. Release any active sessions from the Student Portal or via `DELETE /sessions/{id}`.
2. Stop the Uvicorn process with `Ctrl+C` (or `docker stop openlabscale-demo`).
3. Verify that zero deployment-owned containers remain:
   ```sh
   docker ps -a --filter label=openlabscale.deployment=campus-demo
   docker ps -a --filter label=openlabscale.deployment=demo
   ```
   If an abrupt crash left containers behind, either restart the backend with the **same `deployment` ID** (startup `Engine.reconcile()` automatically removes matching containers before opening admission) or remove them explicitly by label:
   ```sh
   docker rm -f $(docker ps -aq --filter label=openlabscale.deployment=campus-demo) 2>/dev/null || true
   ```

---

## 2. End-to-End Demo Narrative & Verification

With the backend running on `http://127.0.0.1:8000` (and `max_sessions` set to `1` to demonstrate FIFO contention immediately), run the complete student + administrator verification flow:

```sh
api=http://127.0.0.1:8000
alice="Authorization: Bearer token-alice"
bob="Authorization: Bearer token-bob"
admin="Authorization: Bearer token-admin"

# 1. Health & initial admin capacity snapshot
curl -fsS "$api/health"
curl -fsS -H "$admin" "$api/stats" | jq '{active_containers, budget, headroom, reserved, available, queue}'

# 2. Alice requests Session 1 (admitted -> RUNNING); Bob requests Session 2 (queued at #1)
first=$(curl -fsS -H "$alice" -H 'Content-Type: application/json' -d '{}' "$api/sessions" | jq -r .id)
second=$(curl -fsS -H "$bob" -H 'Content-Type: application/json' -d '{}' "$api/sessions" | jq -r .id)
curl -fsS -H "$alice" "$api/sessions/$first" | jq '{id, owner, state, container_id, events}'
curl -fsS -H "$bob" "$api/sessions/$second" | jq '{id, owner, state, queue_position}'

# 3. Verify container isolation flags & cgroup v2 limits
container=$(curl -fsS -H "$alice" "$api/sessions/$first" | jq -r .container_id)
docker inspect "$container" --format '{{.State.Status}} user={{.Config.User}} cpu={{.HostConfig.NanoCpus}} mem={{.HostConfig.Memory}} pids={{.HostConfig.PidsLimit}} net={{.HostConfig.NetworkMode}} ro={{.HostConfig.ReadonlyRootfs}}'

# 4. Verify cross-user & role isolation (Bob cannot read Alice's session; Alice cannot read /stats)
curl -s -o /dev/null -w "bob_read_alice=%{http_code}\n" -H "$bob" "$api/sessions/$first"
curl -s -o /dev/null -w "alice_read_stats=%{http_code}\n" -H "$alice" "$api/stats"

# 5. Admin inspects live container CPU/memory telemetry and FIFO queue
curl -fsS -H "$admin" "$api/stats" | jq '{active_containers, counts, reserved, queue, containers}'

# 6. Alice attaches to WebSocket terminal and executes Linux commands inside the container
FIRST="$first" python - <<'PY'
import os
from websockets.sync.client import connect

with connect(
    f"ws://127.0.0.1:8000/sessions/{os.environ['FIRST']}/terminal",
    subprotocols=["openlabscale", "auth.token-alice"],
) as ws:
    ws.send('{"rows":24,"cols":80}')
    ws.send(b"printf 'workspace-user=%s\\n' \"$(id -u):$(id -g)\"\n")
    output = b""
    while b"workspace-user=65534:65534" not in output:
        output += ws.recv(timeout=5)
    print(output.decode(errors="replace"))
PY

# 7. Alice releases Session 1 -> container is removed and Bob's Session 2 advances to RUNNING
curl -fsS -X DELETE -H "$alice" "$api/sessions/$first" | jq '{id, state}'
curl -fsS -H "$bob" "$api/sessions/$second" | jq '{id, state, container_id}'

# 8. Bob releases Session 2 -> Admin confirms full capacity reclamation and 0 active containers
curl -fsS -X DELETE -H "$bob" "$api/sessions/$second" | jq '{id, state}'
curl -fsS -H "$admin" "$api/stats" | jq '{active_containers, counts, reserved, available, queue}'
```

Expected outcomes:
- `docker inspect` prints `running user=65534:65534 cpu=500000000 mem=268435456 pids=32 net=none ro=true`.
- Cross-user session lookup returns `404` (`bob_read_alice=404`) and student access to `/stats` returns `403` (`alice_read_stats=403`).
- Terminal command prints `workspace-user=65534:65534` and the interactive shell is killed when the WebSocket disconnects.
- Releasing `first` removes its Docker container, advances `second` from `QUEUED` to `RUNNING`, and releasing `second` returns `active_containers: 0` and `reserved: {"cpu_millis": 0, "memory_mib": 0, "slots": 0}`.

---

## 3. AWS EC2 Ubuntu Single-Host Deployment Guide

> **Verification Status Notice**: All backend unit tests, live Docker container/terminal lifecycle checks, and the 10-client / 100-client concurrent load experiments have been executed and verified on the local Linux Docker host (`Linux 6.18.54.1-microsoft-standard-WSL2`, Docker Engine `29.9.2`, cgroup v2). **Live AWS EC2 execution has not been performed from this workstation (no AWS credentials or live EC2 host attached) and is explicitly marked unverified on cloud hardware.** Follow the exact steps below to deploy, verify, and tear down the demo on AWS EC2.

### 3.1 Instance, Storage, and Network Security Configuration

- **AMI**: **Ubuntu Server 24.04 LTS (HVM, SSD Volume Type)** (`x86_64`, Linux kernel 6.8 with cgroup v2 enabled by default).
- **Initial Candidate Instance Type**: **`t3.xlarge`** (`4 vCPU`, `16 GiB RAM`, EBS-Only, Nitro hypervisor) — see Section 4 for sizing evaluation and smaller/compute-optimized alternatives (`t3.large`, `c6i.xlarge`).
- **Root EBS Volume**: `20 GiB` `gp3` (`3000 IOPS`, `125 MB/s`), encrypted, with **`DeleteOnTermination = true`** so terminating the instance deletes the volume automatically.
- **Instance Metadata Service (IMDSv2)**: Require `HttpTokens = required` and set **`HttpPutResponseHopLimit = 1`** so even if networking were enabled in a container, EC2 instance metadata (`169.254.169.254`) cannot cross the container network hop. (OpenLabScale additionally enforces `network_mode="none"` on all student containers.)
- **IAM Instance Profile**: **None** (do not attach an IAM role or store `~/.aws/credentials` on the demo host).
- **Security Group (Private Access Only)**:
  - **Inbound**: Allow **TCP port `22` (SSH)** **only** from your operator workstation public IP (`<YOUR_PUBLIC_IP>/32`). **Do not open port `8000`, `5173`, `2375`, or `2376` in the Security Group.**
  - **Outbound**: Allow HTTPS/HTTP (`443`/`80`) to pull Ubuntu packages, Docker Engine, and the `alpine:latest` image.

### 3.2 Host Setup & Docker Installation on Ubuntu 24.04 LTS

SSH into the EC2 instance (`ssh -i <your-key.pem> ubuntu@<EC2_PUBLIC_IP>`) and run:

```sh
# 1. Configure host firewall (UFW): allow SSH only
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw --force enable
sudo ufw status verbose

# 2. Install Docker Engine, Python venv, Node.js/npm (to build frontend/dist), and jq
sudo apt-get update
sudo apt-get install -y ca-certificates curl git jq python3-venv python3-pip nodejs npm docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
```

Log out and reconnect over SSH so the `docker` group membership takes effect, then verify cgroup v2 and preload the workspace image:

```sh
docker info --format 'OS={{.OSType}} Cgroup={{.CgroupVersion}} CPUs={{.NCPU}} MemBytes={{.MemTotal}}'
docker pull alpine:latest
```

### 3.3 Configure & Start OpenLabScale on EC2 (`t3.xlarge` Profile)

Clone the repository, install Python dependencies, generate strong random bearer tokens, and configure `OPENLABSCALE_CONFIG` for a `4 vCPU` (`4000` mCPU) / `16 GiB` (`16384` MiB) host with `1 vCPU` (`1000` mCPU) and `2 GiB` (`2048` MiB) reserved for host headroom (`6` concurrent `500` mCPU / `256` MiB student containers):

```sh
git clone https://github.com/YdtTran/CloudComputing-OpenLabScale.git
cd CloudComputing-OpenLabScale

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements-test.txt

# Build static React/Vite frontend bundle (served automatically at http://127.0.0.1:8000/)
cd frontend
npm ci
npm run build
cd ..

# Generate random tokens (keep out of committed files and public logs)
export STUDENT_ALICE_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(24))')
export STUDENT_BOB_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(24))')
export ADMIN_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(24))')

printf 'Alice token: %s\nBob token:   %s\nAdmin token: %s\n' \
  "$STUDENT_ALICE_TOKEN" "$STUDENT_BOB_TOKEN" "$ADMIN_TOKEN"

export OPENLABSCALE_CONFIG=$(python - <<'PY'
import json
import os

print(json.dumps({
    "deployment": "ec2-demo",
    "image": "alpine:latest",
    "tokens": {
        os.environ["STUDENT_ALICE_TOKEN"]: "alice",
        os.environ["STUDENT_BOB_TOKEN"]: "bob",
        os.environ["ADMIN_TOKEN"]: "admin",
    },
    "admin": "admin",
    "host_cpu_millis": 4000,
    "headroom_cpu_millis": 1000,
    "host_memory_mib": 16384,
    "headroom_memory_mib": 2048,
    "default_cpu_millis": 500,
    "default_memory_mib": 256,
    "max_sessions": 6,
    "per_user": 2,
    "pids": 32,
    "lifetime_seconds": 900,
    "queue_seconds": 300,
    "terminal_origin": "http://127.0.0.1:8000",
}))
PY
)

# Start single-worker backend + static UI bound strictly to 127.0.0.1:8000
uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

### 3.4 Private Access via SSH Tunnel & Browser Verification

From your **local laptop/workstation**, open an SSH local port forward to the EC2 loopback interface:

```sh
ssh -i <your-key.pem> -N -L 8000:127.0.0.1:8000 ubuntu@<EC2_PUBLIC_IP>
```

Open your local browser at:
- **Student Portal**: `http://127.0.0.1:8000/#student` — Select `Custom Token...` and paste `$STUDENT_ALICE_TOKEN` (or use `openlabscale.env` tokens if running a classroom demo).
- **Admin Dashboard**: `http://127.0.0.1:8000/#admin` — Select `Custom Token...` and paste `$ADMIN_TOKEN`.

Because the browser accesses `http://127.0.0.1:8000` over the SSH tunnel, the WebSocket `Origin` header is `http://127.0.0.1:8000`, matching `terminal_origin` without exposing any public HTTP/WebSocket port on EC2.

To run the live verification and 100-client load suite directly on the EC2 host (in a second SSH session):

```sh
cd ~/CloudComputing-OpenLabScale
. .venv/bin/activate
python -m unittest discover -s tests -v
python -m unittest discover -s backend_tests -v
OPENLABSCALE_LIVE=1 python -m unittest discover -s backend_tests -p test_live.py -v
python -m backend.load suite /tmp/ec2-load-run --smoke-clients 10 --load-clients 100 --max-sessions 6 --job-seconds 1.0
```

---

## 4. Sizing & `t3.xlarge` (4 vCPU, 16 GiB) Candidate Evaluation

### 4.1 Budget, Headroom, and Measured Container Footprint

| Parameter / Metric | Configured / Measured Value | Basis & Operational Implication |
| --- | --- | --- |
| **EC2 Candidate Specs (`t3.xlarge`)** | `4 vCPU` (`4000` mCPU), `16 GiB` (`16384` MiB) | AWS Nitro burstable x86_64 instance |
| **Reserved Host Headroom** | `1000` mCPU (`1.0 vCPU`), `2048` MiB (`2 GiB`) | Reserves capacity for Linux kernel, `sshd`, `dockerd`/`containerd`, and single Uvicorn worker |
| **Allocatable Session Budget** | `3000` mCPU (`3.0 vCPU`), `14336` MiB (`14 GiB`) | Enforced by `Settings.cpu_budget` and `Settings.memory_budget` |
| **Default Session Quota** | `500` mCPU (`0.5 vCPU`), `256` MiB RAM, `32` PIDs | Hard cgroup v2 limits (`cpu.max`, `memory.max`, `memory.swap.max=0`, `pids.max=32`) |
| **CPU-Bound Concurrent Slot Limit** | $\lfloor 3000 / 500 \rfloor = \mathbf{6}$ containers | **Binding bottleneck on `t3.xlarge`** |
| **Memory-Bound Concurrent Slot Limit** | $\lfloor 14336 / 256 \rfloor = 56$ containers | At `6` containers, only `1536` MiB (`1.5 GiB`) is reserved; **`12.5 GiB` of allocatable RAM sits unused** |
| **Measured Idle Container RSS** | `~0.5 – 4.0 MiB` (`alpine:latest` `/bin/sleep` + `/bin/sh`) | Observed via Docker `memory_stats.usage` in `GET /stats` |
| **Measured Provisioning Latency** | `p50 = 270.23 ms`, `p95 = 341.24 ms` (`max = 483.22 ms`) | Measured across 100 real containers in `data/load-v1/concurrent-100` |
| **Measured Release/Cleanup Latency** | `p50 = 247.74 ms`, `p95 = 568.99 ms` (`max = 791.59 ms`) | Forced removal (`docker rm -f`) before capacity return |

### 4.2 AWS Burstable CPU-Credit Behavior (`t3.xlarge`)

`t3.xlarge` is a **burstable performance instance** governed by AWS CPU credits (`1 CPU credit = 1 vCPU running at 100% for 1 minute`):

- **Baseline utilization**: `40%` per vCPU $\times 4\text{ vCPU} = \mathbf{1.6\text{ vCPU}}$ (`1600` mCPU continuous host-wide baseline).
- **Credit earn rate & cap**: Accrues **`96` CPU credits/hour** (`1.6` credits/minute) up to a maximum balance of **`2304` credits**.
- **Interactive classroom behavior (Credit-positive)**: Interactive shell sessions spend most of their lifetime idle (`< 1%` CPU), with brief command bursts. Aggregate host CPU stays well below `1.6 vCPU`, so `t3.xlarge` accrues credits continuously with zero surplus cost.
- **Sustained CPU-bound behavior (Credit-depleting)**: If all `6` admitted containers saturate their `500` mCPU quota simultaneously (`3000` mCPU) plus `~400` mCPU host/daemon overhead (`3.4 vCPU` total = `85%` host utilization), the instance burns $3.4 - 1.6 = \mathbf{1.8\text{ CPU credits/minute}}$ (`108` credits/hour):
  - In **`unlimited` mode** (AWS default for T3): Once accrued credits deplete, AWS bills **surplus credits at `$0.05` per vCPU-hour**.
  - In **`standard` mode**: Once credits deplete, AWS throttles the entire host down to the `1.6 vCPU` (`1600` mCPU) baseline, starving containers that were promised `3000` mCPU by the scheduler and increasing Docker daemon latencies.
- **100-request batch load impact**: The `concurrent-100` workload (`100` sessions $\times$ `1.0s` hold) completes in `~35–65` seconds and consumes **under `4` CPU credits total**, well within initial launch/accrued credits.

### 4.3 Sizing Recommendation

1. **For short classroom demos and interactive shell labs (1–3 hours)**: `t3.xlarge` works reliably at `max_sessions = 6`, `500` mCPU, `256` MiB, but **wastes ~`12.5 GiB` of RAM**.
2. **Cost-reduced burstable alternative**: If `4–6` concurrent containers are sufficient, **`t3.large` (`2 vCPU`, `8 GiB RAM`, `~$0.0832/hr`)** at `250–350` mCPU per session or **`c7i-flex.xlarge` / `c6i.xlarge` (`4 vCPU`, `8 GiB RAM`)** matches the 2:1 memory-to-CPU ratio of `500` mCPU / `256` MiB containers without paying for `16 GiB` of memory.
3. **For sustained CPU-intensive student workloads**: Prefer a fixed-performance compute instance (`c6i.xlarge` or `c7i.xlarge`, `4 vCPU`, `8 GiB RAM`) to eliminate T3 CPU-credit throttling and surplus charges.

---

## 5. Security Controls, Trust Boundaries & Known Limitations

- **Docker Socket Privilege Boundary**: The backend requires `unix:///var/run/docker.sock` (`backend/api.py` rejects non-Unix `DOCKER_HOST` URLs). Student containers never receive the Docker socket, host bind mounts (`Mounts: []`), or host environment variables.
- **Container Sandbox Hardening**: Every session container is created with `user="65534:65534"`, `privileged=False`, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges:true"]`, `network_mode="none"`, `read_only=True`, a bounded `/tmp` tmpfs (`rw,noexec,nosuid,nodev,size=16m,mode=1777`), `nano_cpus`, `mem_limit == memswap_limit` (swap disabled), `pids_limit=32`, `init=True`, and a finite `/bin/sleep <lifetime_seconds>` entrypoint.
- **Demo-Only Static Identity**: Authentication uses static bearer tokens mapped in `OPENLABSCALE_CONFIG.tokens`. There is no OAuth/OIDC, TLS termination, password hashing, token rotation, or rate limiting. Never commit live tokens, pass tokens in query strings, or expose the service directly to the public internet.
- **Shared-Kernel Untrusted-Code Limitation**: Standard Docker containers share the host Linux kernel. While `cap_drop=["ALL"]`, `no-new-privileges`, `network_mode="none"`, cgroup v2 limits, and `65534:65534` restrict container capabilities, this single-host architecture is designed for **controlled academic demonstrations**, not hostile multi-tenant public execution (which would require microVM isolation such as Firecracker/gVisor and multi-node isolation).
- **Single-Process In-Memory Ledger**: Queue state and session history live in process memory (`--workers 1`) and reset on backend restart. Startup `Engine.reconcile()` removes leftover containers labeled `openlabscale.deployment=<deployment>` and checks `~/.cache/openlabscale/<deployment>/*.create` markers before accepting requests.

---

## 6. Cloud Cost Controls, Logging & Safe Teardown

### 6.1 Cost Breakdown (US East `us-east-1` On-Demand Reference)

| Resource | Approximate Rate | Billing Behavior when Instance is `Stopped` vs `Terminated` |
| --- | --- | --- |
| **`t3.xlarge` compute** | `~$0.1664 / hour` (`~$3.99 / day`) | **Stops billing** when `stopped` or `terminated` |
| **`20 GiB` `gp3` EBS volume** | `$0.08 / GiB-month` (`~$1.60 / month`) | **Continues billing while `stopped`**; stops only when volume is deleted (`terminated`) |
| **Public IPv4 address** | `$0.005 / hour` (`~$3.65 / month`) | Billed while associated; released on termination (unless using an unattached Elastic IP) |
| **T3 Unlimited surplus CPU** | `$0.05 / vCPU-hour` above `40%` baseline | Incurred only if sustained CPU exceeds accrued credits in `unlimited` mode |

To prevent unexpected surplus CPU charges during testing, you can switch the instance to `standard` credit mode:

```sh
aws ec2 modify-instance-credit-specification \
  --instance-credit-specification "InstanceId=<INSTANCE_ID>,CpuCredits=standard"
```

### 6.2 Logging & Cleanup on Host

Redirect Uvicorn output to a local log file (with `0600` permissions) during demonstrations:

```sh
umask 077
uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 \
  2>&1 | tee -a ~/openlabscale-backend.log
```

Before shutting down the EC2 instance, clean up all demo containers and cached images:

```sh
# 1. Stop Uvicorn (Ctrl+C), then remove any remaining demo-owned containers
docker rm -f $(docker ps -aq --filter label=openlabscale.deployment=ec2-demo) 2>/dev/null || true
docker ps -a --filter label=openlabscale.deployment=ec2-demo

# 2. Optional: prune unused images and build cache
docker image rm alpine:latest 2>/dev/null || true
docker system prune -f
```

### 6.3 Stopping vs. Terminating the EC2 Environment

From your workstation with AWS CLI configured:

```sh
# Option A: Stop instance temporarily (stops EC2 hourly compute charge; $1.60/mo EBS charge continues)
aws ec2 stop-instances --instance-ids <INSTANCE_ID>

# Option B: Terminate instance permanently after demo (stops ALL compute, EBS, and IPv4 charges)
aws ec2 terminate-instances --instance-ids <INSTANCE_ID>

# Verify instance reaches 'terminated' and no leftover EBS volumes or Elastic IPs remain
aws ec2 describe-instances --instance-ids <INSTANCE_ID> \
  --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name}' --output table
aws ec2 describe-volumes --filters Name=attachment.instance-id,Values=<INSTANCE_ID> \
  --query 'Volumes[].{VolumeId:VolumeId,State:State}' --output table
```

---

## 7. API Reference

HTTP authentication uses `Authorization: Bearer <token>`. Session reads and releases require the owning identity. Invalid credentials return `401`. Unknown and other-owned sessions return the same `404`. Validation failures return `422` with `detail` and `errors`.

| Method and path | Behavior |
| --- | --- |
| `GET /` | Serves the compiled Student Portal (`/#student`) and Administrator Dashboard (`/#admin`) when `frontend/dist/index.html` is present. |
| `POST /sessions` | Submit `{}` for defaults or `{"cpu_millis":500,"memory_mib":256}`. Returns HTTP `202` and a `Session` with `id`, `owner`, `state`, resource limits, queue position/wait, lifecycle events, and nullable container/failure fields. Impossible requests return `422`. |
| `GET /sessions` | List the caller's sessions, including terminal states. |
| `GET /sessions/{id}` | Read one owned session (`queue_position` is one-based while queued). |
| `DELETE /sessions/{id}` | Request idempotent release or queue cancellation (`HTTP 202`). |
| `GET /stats` | Admin-only queue, state counts, session history, scheduler budgets/reservations/headroom, and live Docker + `/proc` measurements. |
| `GET /health` | Public liveness and scheduler availability (`200` or `503`). |
| `WS /sessions/{id}/terminal` | Attach interactive PTY for an owned `RUNNING` session using subprotocols `["openlabscale", "auth.<token>"]`. Binary frames carry terminal I/O; JSON text `{"rows":24,"cols":80}` resizes the PTY. |

---

## 8. Configuration Reference (`OPENLABSCALE_CONFIG`)

| Key | Default / meaning |
| --- | --- |
| `deployment`, `tokens`, `admin` | Required. Stable deployment label (`^[a-z0-9][a-z0-9-]{0,39}$`), bearer-token-to-identity map, and administrator identity. |
| `image` | `alpine:latest`. Preloaded local Linux image with BusyBox-compatible `/bin/sh` and `/bin/sleep` and no declared volumes. |
| `host_cpu_millis`, `headroom_cpu_millis` | `2000` and `500` (`1000` millis = `1` vCPU). Scheduler admits against `host_cpu_millis - headroom_cpu_millis`. |
| `host_memory_mib`, `headroom_memory_mib` | `2048` and `512` MiB. Scheduler admits against `host_memory_mib - headroom_memory_mib`. |
| `default_cpu_millis`, `default_memory_mib` | `500` mCPU and `256` MiB per request (minimum override: `10` mCPU, `6` MiB). |
| `max_sessions`, `per_user`, `pids` | `20` global slots, `2` active/reserved slots per user, `32` PIDs per container (minimum `8`). |
| `lifetime_seconds`, `queue_seconds` | `900` seconds running and `300` seconds queued before automatic expiry. |
| `poll_seconds`, `docker_timeout_seconds` | `1` second between scheduler maintenance passes and `10` seconds per Docker SDK call. |
| `terminal_origin` | `http://127.0.0.1:8000`. Enforced when the browser sends an `Origin` header on WebSocket upgrade. |

---

## 9. Concurrent Request-Load Experiment (`data/load-v1/`)

`backend/load.py` runs synchronized `asyncio` + `httpx` clients that submit `POST /sessions` concurrently, poll `GET /sessions/{id}` until `RUNNING`, hold each disposable container for a bounded `job_seconds` duration, and call `DELETE /sessions/{id}` with automatic cleanup on timeout or error so the FIFO queue drains completely. An administrator sampler polls `GET /stats` concurrently and reconciles client outcomes against server lifecycle counts and remaining owned Docker containers.

```sh
python -m backend.load suite /tmp/load-run --smoke-clients 10 --load-clients 100 --max-sessions 4 --job-seconds 1.0
```

Retained evidence from the verified local Linux Docker run (`2026-11-09`, Linux `6.18.54.1-microsoft-standard-WSL2`, Docker Engine `29.9.2`, cgroup v2, 16 vCPU, 7.39 GiB RAM, `alpine:latest`, `host_cpu_millis=2500`, `headroom_cpu_millis=500`, `host_memory_mib=2048`, `headroom_memory_mib=512`, `500` CPU millis and `256` MiB per session, `max_sessions=4`, `job_seconds=1.0`) is stored under `data/load-v1/`:

| Run | Concurrent HTTP clients | Active terminals | Configured container cap | Peak running containers | Released / Failed / Timed out | Admission latency p50 / p95 (ms) | Queue wait p50 / p95 (ms) | Provisioning p50 / p95 (ms) | Completion p50 / p95 (ms) | Cleanup verified |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `data/load-v1/smoke-10` | 10 | 0 | 4 | 4 | 10 / 0 / 0 | 42.80 / 45.58 | 1556.46 / 3312.36 | 202.94 / 236.47 | 3092.32 / 4740.69 | Yes (`0` remaining) |
| `data/load-v1/concurrent-100` | 100 | 0 | 4 | 4 | 100 / 0 / 0 | 285.41 / 315.93 | 34569.21 / 60682.52 | 270.23 / 341.24 | 37326.47 / 62582.87 | Yes (`0` remaining) |

**Important distinction:** `concurrent-100` measures **100 simultaneous HTTP clients** submitting `POST /sessions` requests against a cap of **4 concurrently running containers** (with **0 active browser terminals**). Excess requests remain `QUEUED` (`peak_queued_sessions = 100`) and advance in FIFO order as bounded jobs release capacity.

---

## 10. Regression & Live Test Commands

```sh
# 1. Offline simulation & measured v1 contract tests (45 tests, stdlib only)
python3 -m unittest discover -s tests -v

# 2. Retained v1 bundle validation
python3 -m simulation validate data/simulation-v1/dev-43
python3 -m simulation validate data/simulation-v1/heldout-44
python3 -m simulation validate data/simulation-v1/scale-120
python3 -m simulation validate data/measured-v1/debian-first-run
python3 -m tests.live_measured verify data/measured-v1/debian-first-run

# 3. OpenLabScale backend unit + load workflow tests
python -m unittest discover -s backend_tests -v

# 4. Live Linux Docker container, terminal PTY, FIFO queue, and orphan-reconciliation test
OPENLABSCALE_LIVE=1 python -m unittest discover -s backend_tests -p test_live.py -v
```
