"""Mock Workload Generator for OpenLab-Scale.

Simulates a client application requesting a license seat from the License Manager,
holding it for a configurable duration with periodic heartbeats, and releasing
it gracefully upon completion or termination.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
import urllib.error
import urllib.request
import uuid

LICENSE_MANAGER_URL = os.getenv("LICENSE_MANAGER_URL", "http://license-manager:8000").rstrip("/")
WORKLOAD_ID = os.getenv("WORKLOAD_ID", f"workload-{uuid.uuid4().hex[:8]}")
HOLD_TIME_SEC = int(os.getenv("HOLD_TIME_SEC", "30"))
HEARTBEAT_INTERVAL_SEC = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "10"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] [mock-workload] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("mock-workload")

running = True
current_lease_id: str | None = None


def handle_termination(signum, frame):
    global running
    logger.info("Termination signal (%d) received. Releasing lease and shutting down...", signum)
    running = False


signal.signal(signal.SIGINT, handle_termination)
signal.signal(signal.SIGTERM, handle_termination)


def post_json(endpoint: str, data: dict) -> dict:
    url = f"{LICENSE_MANAGER_URL}{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": f"mock-workload/{WORKLOAD_ID}"},
    )
    with urllib.request.urlopen(req, timeout=5.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def acquire_license() -> str | None:
    logger.info("Requesting seat lease for workload %s...", WORKLOAD_ID)
    try:
        resp = post_json(
            "/api/v1/licenses/request",
            {
                "workload_id": WORKLOAD_ID,
                "ttl_seconds": max(60, HOLD_TIME_SEC + 30),
                "metadata": {"simulation": True, "hold_time_sec": HOLD_TIME_SEC},
            },
        )
        if resp.get("success"):
            lease_id = resp["lease_id"]
            logger.info(
                "Lease acquired successfully: lease_id=%s (active seats=%s, remaining=%s)",
                lease_id,
                resp.get("active_seats"),
                resp.get("remaining_seats"),
            )
            return lease_id
        else:
            logger.error("Failed to acquire lease: %s", resp)
            return None
    except urllib.error.HTTPError as http_err:
        body = http_err.read().decode("utf-8", errors="ignore")
        logger.error("HTTP error acquiring license (%d): %s", http_err.code, body)
        return None
    except Exception as exc:
        logger.error("Exception acquiring license: %s", exc)
        return None


def release_license(lease_id: str):
    logger.info("Releasing lease %s for workload %s...", lease_id, WORKLOAD_ID)
    try:
        resp = post_json(
            "/api/v1/licenses/release",
            {"lease_id": lease_id, "workload_id": WORKLOAD_ID},
        )
        logger.info("Release result: %s", resp)
    except Exception as exc:
        logger.warning("Error releasing lease: %s", exc)


def send_heartbeat(lease_id: str):
    logger.info("Sending heartbeat for lease %s...", lease_id)
    try:
        resp = post_json(
            "/api/v1/licenses/heartbeat",
            {"lease_id": lease_id, "workload_id": WORKLOAD_ID},
        )
        logger.info("Heartbeat acknowledged: %s", resp)
    except Exception as exc:
        logger.warning("Heartbeat failed: %s", exc)


def main():
    global current_lease_id, running
    logger.info("Starting mock workload simulation (workload_id=%s, hold_time=%ds)", WORKLOAD_ID, HOLD_TIME_SEC)

    # Wait for license manager to be ready
    ready = False
    for _ in range(30):
        try:
            req = urllib.request.Request(f"{LICENSE_MANAGER_URL}/health")
            with urllib.request.urlopen(req, timeout=2.0) as r:
                if r.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(1)

    if not ready:
        logger.error("License manager at %s is not reachable.", LICENSE_MANAGER_URL)
        sys.exit(1)

    current_lease_id = acquire_license()
    if not current_lease_id:
        logger.error("Could not obtain license seat. Terminating.")
        sys.exit(2)

    start_time = time.time()
    last_heartbeat = start_time

    try:
        while running:
            now = time.time()
            elapsed = now - start_time
            if HOLD_TIME_SEC > 0 and elapsed >= HOLD_TIME_SEC:
                logger.info("Hold duration of %ds reached. Completing workload execution.", HOLD_TIME_SEC)
                break

            if now - last_heartbeat >= HEARTBEAT_INTERVAL_SEC:
                send_heartbeat(current_lease_id)
                last_heartbeat = now

            time.sleep(1)
    finally:
        if current_lease_id:
            release_license(current_lease_id)
            current_lease_id = None
        logger.info("Mock workload finished successfully.")


if __name__ == "__main__":
    main()
