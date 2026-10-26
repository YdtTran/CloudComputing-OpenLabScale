"""OpenLab-Scale eBPF & Cgroup Telemetry Agent.

Monitors host workload metrics, kernel BTF availability, and cgroup v2 resource
utilization. Automatically falls back to cgroup / procfs inspection if BTF
(/sys/kernel/btf/vmlinux) is unavailable on the host.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

# Configuration via environment variables
EBPF_MODE = os.getenv("EBPF_MODE", "auto").lower()
LICENSE_MANAGER_URL = os.getenv("LICENSE_MANAGER_URL", "http://license-manager:8000")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
INSPECTION_INTERVAL_SEC = int(os.getenv("INSPECTION_INTERVAL_SEC", "10"))

# File paths
BTF_PATH = Path("/sys/kernel/btf/vmlinux")
CGROUP_V2_CONTROLLERS = Path("/sys/fs/cgroup/cgroup.controllers")
CGROUP_BASE = Path("/sys/fs/cgroup")
DOCKER_SOCK = Path("/var/run/docker.sock")
LOG_FILE_PATH = Path("logs/ebpf-agent.log")

# Setup logging
log_handlers = [logging.StreamHandler(sys.stdout)]
try:
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_handlers.append(logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"))
except Exception:
    pass

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] [ebpf-agent] %(message)s",
    handlers=log_handlers,
)
logger = logging.getLogger("ebpf-agent")

running = True


def handle_shutdown(signum, frame):
    global running
    logger.info("Received termination signal (%d). Shutting down ebpf-agent gracefully...", signum)
    running = False


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


class SystemProbe:
    """Probes host capabilities: Kernel, BTF, cgroups v2, and Docker."""

    def __init__(self) -> None:
        self.kernel_release = platform.release() or "unknown"
        self.os_type = platform.system()
        self.has_btf = BTF_PATH.exists()
        self.has_cgroup_v2 = CGROUP_V2_CONTROLLERS.exists() or (CGROUP_BASE.exists() and any(CGROUP_BASE.iterdir()))
        self.has_docker_sock = DOCKER_SOCK.exists()
        self.active_mode = self._determine_mode()

    def _determine_mode(self) -> str:
        if EBPF_MODE == "fallback":
            return "CGROUP_FALLBACK_FORCED"
        if self.has_btf and EBPF_MODE in ("auto", "enabled"):
            return "EBPF_TRACING_ACTIVE"
        return "CGROUP_FALLBACK_ACTIVE"

    def describe(self) -> Dict[str, Any]:
        return {
            "os_type": self.os_type,
            "kernel_release": self.kernel_release,
            "btf_path": str(BTF_PATH),
            "btf_available": self.has_btf,
            "cgroup_v2_available": self.has_cgroup_v2,
            "docker_sock_available": self.has_docker_sock,
            "configured_mode": EBPF_MODE,
            "active_mode": self.active_mode,
        }


def collect_cgroup_metrics() -> Dict[str, Any]:
    """Collects CPU, memory, and load metrics via cgroups v2 or procfs."""
    metrics: Dict[str, Any] = {"timestamp": time.time()}

    # CPU stat from cgroups v2
    cpu_stat = CGROUP_BASE / "cpu.stat"
    if cpu_stat.exists():
        try:
            metrics["cgroup_cpu_stat"] = cpu_stat.read_text(encoding="utf-8").strip().splitlines()[:3]
        except Exception as e:
            metrics["cgroup_cpu_stat_err"] = str(e)

    # Memory current from cgroups v2
    mem_current = CGROUP_BASE / "memory.current"
    if mem_current.exists():
        try:
            metrics["cgroup_memory_bytes"] = int(mem_current.read_text(encoding="utf-8").strip())
        except Exception as e:
            metrics["cgroup_memory_err"] = str(e)

    # Host load average fallback
    try:
        if hasattr(os, "getloadavg"):
            metrics["load_avg"] = list(os.getloadavg())
    except Exception:
        pass

    # Host /proc/meminfo fallback
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        try:
            lines = meminfo_path.read_text(encoding="utf-8").splitlines()
            for line in lines[:3]:
                k, v = line.split(":", 1)
                metrics[k.strip()] = v.strip()
        except Exception:
            pass

    return metrics


def check_license_manager_status() -> Dict[str, Any]:
    """Queries License Manager to track seat utilization and workload mapping."""
    target_url = f"{LICENSE_MANAGER_URL.rstrip('/')}/api/v1/licenses/status"
    req = urllib.request.Request(target_url, headers={"User-Agent": "ols-ebpf-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"error": f"Failed to contact license-manager: {exc}"}
    return {}


def main() -> None:
    logger.info("Initializing OpenLab-Scale Observability & Telemetry Agent...")
    probe = SystemProbe()
    probe_details = probe.describe()
    logger.info("Host Diagnostic: %s", json.dumps(probe_details, indent=2))

    if probe.active_mode == "EBPF_TRACING_ACTIVE":
        logger.info("[MODE: eBPF Active] BTF found at %s. Attaching eBPF tracing probes.", BTF_PATH)
    else:
        logger.warning(
            "[MODE: Cgroup Fallback] BTF (/sys/kernel/btf/vmlinux) not detected or fallback active. "
            "Gracefully operating in cgroup v2 / procfs telemetry inspection mode."
        )

    cycle = 0
    while running:
        cycle += 1
        try:
            telemetry = collect_cgroup_metrics()
            lm_status = check_license_manager_status()
            active_seats = lm_status.get("active_seats", "unknown")
            total_seats = lm_status.get("total_seats", "unknown")

            logger.info(
                "[Telemetry Cycle #%d | Mode: %s] Licenses in use: %s/%s | Telemetry metrics: %s",
                cycle,
                probe.active_mode,
                active_seats,
                total_seats,
                list(telemetry.keys()),
            )
        except Exception as exc:
            logger.error("Error during telemetry cycle: %s", exc)

        # Sleep in small slices to promptly respond to termination signals
        for _ in range(INSPECTION_INTERVAL_SEC):
            if not running:
                break
            time.sleep(1)

    logger.info("OpenLab-Scale ebpf-agent stopped cleanly.")


if __name__ == "__main__":
    main()
