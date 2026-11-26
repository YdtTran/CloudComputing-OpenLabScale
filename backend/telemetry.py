from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .engine import LABEL, SESSION_LABEL
from .models import Session, Settings, State

log = logging.getLogger(__name__)
HISTORY_LIMIT = 30
INTERACTION_THROTTLE_SECONDS = 0.25


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_cgroup_v2(pid: int) -> Optional[dict[str, Any]]:
    """Read Linux cgroup v2 CPU, memory, block I/O, and PSI counters for a container PID."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        lines = Path(f"/proc/{pid}/cgroup").read_text().splitlines()
        paths = [line[3:] for line in lines if line.startswith("0::")]
        if len(paths) != 1 or ".." in Path(paths[0]).parts:
            return None
        cg_path = Path("/sys/fs/cgroup") / paths[0].lstrip("/")
        if not cg_path.is_dir():
            return None
        cgroup_id = cg_path.stat().st_ino
        cpu_stat = dict(item.split()[:2] for item in (cg_path / "cpu.stat").read_text().splitlines() if item.strip())
        usage_usec = int(cpu_stat["usage_usec"])
        cpu_max_parts = (cg_path / "cpu.max").read_text().split()
        quota_ratio: Optional[float] = None
        if len(cpu_max_parts) == 2 and cpu_max_parts[0] != "max":
            quota, period = int(cpu_max_parts[0]), int(cpu_max_parts[1])
            if quota > 0 and period > 0:
                quota_ratio = quota / period
        memory_bytes = int((cg_path / "memory.current").read_text().strip())

        blk_read = blk_write = blk_rios = blk_wios = 0
        io_stat_path = cg_path / "io.stat"
        if io_stat_path.is_file():
            for line in io_stat_path.read_text().splitlines():
                for token in line.split()[1:]:
                    if "=" not in token:
                        continue
                    k, v = token.split("=", 1)
                    if k == "rbytes":
                        blk_read += int(v)
                    elif k == "wbytes":
                        blk_write += int(v)
                    elif k == "rios":
                        blk_rios += int(v)
                    elif k == "wios":
                        blk_wios += int(v)

        def read_psi_avg10(filename: str) -> Optional[float]:
            p = cg_path / filename
            if not p.is_file():
                return None
            for line in p.read_text().splitlines():
                if line.startswith("some "):
                    for token in line.split()[1:]:
                        if token.startswith("avg10="):
                            return float(token.split("=", 1)[1])
            return None

        return {
            "cgroup_id": cgroup_id,
            "usage_ns": usage_usec * 1000,
            "quota_ratio": quota_ratio,
            "memory_bytes": memory_bytes,
            "blk_read_bytes": blk_read,
            "blk_write_bytes": blk_write,
            "blk_io_ops": blk_rios + blk_wios,
            "psi_cpu_some_avg10": read_psi_avg10("cpu.pressure"),
            "psi_io_some_avg10": read_psi_avg10("io.pressure"),
            "mono_ns": time.monotonic_ns(),
        }
    except (OSError, ValueError, KeyError):
        return None


class EbpfSupervisor:
    """Manage one deployment-scoped confined eBPF collector container over Docker API."""

    def __init__(self, settings: Settings, client: Any):
        self.settings = settings
        self.client = client
        self.container_name = f"openlabscale-{settings.deployment}-collector"
        self.container = None
        self.stdin_sock = None
        self.raw_sock = None
        self.attach_stream = None
        self.reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stopping = False
        self._tracked: set[int] = set()
        self.status = "UNAVAILABLE"
        self.reason = "Not started"
        self.probes: list[str] = []
        self.loss_count: Optional[int] = None
        self.last_snapshot_mono: Optional[float] = None
        self.last_snapshot_at: Optional[str] = None
        self.cgroups: dict[int, dict[str, Any]] = {}
        self.recent_comm: dict[int, str] = {}

    def _cleanup_existing(self) -> None:
        containers = self.client.containers.list(
            all=True,
            ignore_removed=True,
            filters={"label": [f"{LABEL}={self.settings.deployment}", "openlabscale.role=collector"]},
        )
        for item in containers:
            try:
                item.remove(force=True)
            except Exception:
                log.warning("Failed removing stale collector container %s", getattr(item, "id", "?"))

    def start(self) -> None:
        self._stopping = False
        with self._lock:
            self.status = "STARTING"
            self.reason = "Starting confined eBPF collector container"
        try:
            self._cleanup_existing()
            container = self.client.containers.create(
                self.settings.collector_image,
                ["--live", "--interval-ms", "1000"],
                name=self.container_name,
                labels={LABEL: self.settings.deployment, "openlabscale.role": "collector"},
                cap_drop=["ALL"],
                cap_add=["BPF", "PERFMON"],
                pid_mode="host",
                cgroupns="host",
                network_mode="none",
                read_only=True,
                security_opt=["no-new-privileges:true"],
                stdin_open=True,
                volumes={
                    "/sys/kernel/tracing": {"bind": "/sys/kernel/tracing", "mode": "ro"},
                    "/sys/kernel/btf": {"bind": "/sys/kernel/btf", "mode": "ro"},
                    "/sys/fs/cgroup": {"bind": "/sys/fs/cgroup", "mode": "ro"},
                },
            )
            self.container = container
            container.start()
            stdin_sock = self.client.api.attach_socket(container.id, params={"stdin": 1, "stream": 1})
            self.stdin_sock = stdin_sock
            self.raw_sock = getattr(stdin_sock, "_sock", stdin_sock)
            stream = container.attach(stdout=True, stderr=True, stream=True, logs=True)
            self.attach_stream = stream
            ready_event = threading.Event()

            def read_loop() -> None:
                buf = b""
                try:
                    for chunk in stream:
                        if self._stopping:
                            break
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            text = line.decode("utf-8", errors="replace").strip()
                            if not text:
                                continue
                            try:
                                msg = json.loads(text)
                            except ValueError:
                                continue
                            self._handle_message(msg, ready_event)
                except Exception as exc:
                    if not self._stopping:
                        with self._lock:
                            self.status = "UNAVAILABLE"
                            self.reason = f"eBPF collector stream ended: {exc}"
                finally:
                    if not self._stopping:
                        with self._lock:
                            if self.status in ("OK", "STARTING"):
                                self.status = "UNAVAILABLE"
                                self.reason = "eBPF collector exited unexpectedly"
                    ready_event.set()

            self.reader_thread = threading.Thread(target=read_loop, daemon=True)
            self.reader_thread.start()
            if not ready_event.wait(timeout=8.0):
                raise RuntimeError("Timed out waiting for eBPF collector attachment readiness")
            with self._lock:
                if not self.probes:
                    raise RuntimeError(self.reason or "eBPF collector exited before attaching probes")
        except Exception as exc:
            log.warning("eBPF collector unavailable: %s", exc)
            with self._lock:
                self.status = "UNAVAILABLE"
                self.reason = str(exc)
            self.stop(keep_reason=True)

    def _handle_message(self, msg: dict[str, Any], ready_event: threading.Event) -> None:
        mtype = msg.get("type")
        with self._lock:
            if mtype == "ready":
                self.probes = list(msg.get("probes") or [])
                self.status = "OK"
                self.reason = "Attached eBPF CO-RE probes"
                ready_event.set()
            elif mtype == "exec":
                cgid = msg.get("cgroup_id")
                comm = msg.get("comm")
                if isinstance(cgid, int) and comm:
                    self.recent_comm[cgid] = str(comm)
            elif mtype == "snapshot":
                self.last_snapshot_mono = time.monotonic()
                self.last_snapshot_at = utc_iso()
                self.loss_count = msg.get("loss_count")
                parsed: dict[int, dict[str, Any]] = {}
                for k, v in (msg.get("cgroups") or {}).items():
                    try:
                        parsed[int(k)] = v
                    except (TypeError, ValueError):
                        continue
                self.cgroups = parsed
                if self.status != "OK" and self.probes:
                    self.status = "OK"
                    self.reason = "Receiving eBPF kernel snapshots"

    def sync_cgroups(self, desired_ids: set[int]) -> None:
        with self._lock:
            if self.raw_sock is None or self.status not in ("OK", "STARTING"):
                return
            to_add = sorted(desired_ids - self._tracked)
            to_del = sorted(self._tracked - desired_ids)
            if not to_add and not to_del:
                return
            payload = "".join(f"+ {cid}\n" for cid in to_add) + "".join(f"- {cid}\n" for cid in to_del)
            try:
                self.raw_sock.sendall(payload.encode("ascii"))
                self._tracked.update(to_add)
                self._tracked.difference_update(to_del)
                for cid in to_del:
                    self.recent_comm.pop(cid, None)
            except OSError as exc:
                self.status = "UNAVAILABLE"
                self.reason = f"eBPF control write failed: {exc}"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self.status,
                "reason": self.reason,
                "probes": list(self.probes),
                "loss_count": self.loss_count,
                "last_snapshot_mono": self.last_snapshot_mono,
                "last_snapshot_at": self.last_snapshot_at,
                "cgroups": {k: dict(v) for k, v in self.cgroups.items()},
                "recent_comm": dict(self.recent_comm),
                "tracked_cgroups": sorted(self._tracked),
            }

    def stop(self, keep_reason: bool = False) -> None:
        self._stopping = True
        with self._lock:
            raw = self.raw_sock
            sock = self.stdin_sock
            stream = self.attach_stream
            container = self.container
            self.raw_sock = None
            self.stdin_sock = None
            self.attach_stream = None
            self.container = None
            self._tracked.clear()
            if not keep_reason:
                self.status = "UNAVAILABLE"
                self.reason = "Collector stopped"
        if raw is not None:
            try:
                raw.sendall(b"quit\n")
            except OSError:
                pass
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
        if sock is not None:
            resp = getattr(sock, "_response", None)
            try:
                if resp is not None:
                    resp.close()
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
        if self.reader_thread is not None and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=2.0)


class ObservabilityTracker:
    """Aggregate cgroup v2, live eBPF counters, and browser interactions into read-only recommendations."""

    def __init__(self, settings: Settings, engine: Any = None):
        self.settings = settings
        self.engine = engine
        self._lock = threading.Lock()
        self._interactions: dict[str, tuple[float, str, str]] = {}
        self._baselines: dict[str, dict[str, Any]] = {}
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._pid_cache: dict[str, int] = {}
        self._ebpf_supervisor: Optional[EbpfSupervisor] = None
        if settings.enable_ebpf and engine is not None and hasattr(engine, "client"):
            self._ebpf_supervisor = EbpfSupervisor(settings, engine.client)

    def start(self) -> None:
        if self._ebpf_supervisor is not None:
            self._ebpf_supervisor.start()

    def stop(self) -> None:
        if self._ebpf_supervisor is not None:
            self._ebpf_supervisor.stop()

    def record_interaction(
        self,
        session_id: str,
        source: str = "terminal_input",
        now_mono: Optional[float] = None,
        now_utc: Optional[str] = None,
    ) -> None:
        mono = time.monotonic() if now_mono is None else now_mono
        iso = utc_iso() if now_utc is None else now_utc
        with self._lock:
            prev = self._interactions.get(session_id)
            if prev is not None and prev[2] == source and (mono - prev[0]) < INTERACTION_THROTTLE_SECONDS:
                return
            self._interactions[session_id] = (mono, iso, source)

    def _resolve_pid(self, session: Session) -> Optional[int]:
        if not session.container_id or self.engine is None:
            return None
        cached = self._pid_cache.get(session.container_id)
        if cached is not None:
            return cached
        try:
            info = self.engine.client.api.inspect_container(session.container_id)
            pid = info.get("State", {}).get("Pid")
            if isinstance(pid, int) and pid > 0:
                self._pid_cache[session.container_id] = pid
                return pid
        except Exception:
            return None
        return None

    def observe(
        self,
        sessions: list[Session],
        container_samples: Optional[dict[str, dict[str, Any]]],
        *,
        ebpf_snapshot: Optional[dict[str, Any]] = None,
        cgroup_reader: Callable[[int], Optional[dict[str, Any]]] = read_cgroup_v2,
        pid_lookup: Optional[Callable[[Session], Optional[int]]] = None,
        now_mono: Optional[float] = None,
        now_utc: Optional[str] = None,
    ) -> dict[str, Any]:
        mono = time.monotonic() if now_mono is None else now_mono
        iso = utc_iso() if now_utc is None else now_utc
        active_sessions = [s for s in sessions if s.state == State.RUNNING]
        active_ids = {s.id for s in active_sessions}
        active_cids = {s.container_id for s in active_sessions if s.container_id}

        lookup = pid_lookup or self._resolve_pid
        cgroup_samples: dict[str, dict[str, Any]] = {}
        desired_cgids: set[int] = set()
        for s in active_sessions:
            pid = lookup(s)
            if pid:
                cg = cgroup_reader(pid)
                if cg is not None:
                    cgroup_samples[s.id] = cg
                    desired_cgids.add(cg["cgroup_id"])

        if ebpf_snapshot is None:
            if self._ebpf_supervisor is not None:
                self._ebpf_supervisor.sync_cgroups(desired_cgids)
                ebpf_snapshot = self._ebpf_supervisor.snapshot()
            else:
                ebpf_snapshot = {
                    "status": "UNAVAILABLE",
                    "reason": "eBPF collector disabled" if not self.settings.enable_ebpf else "eBPF collector not started",
                    "probes": [],
                    "loss_count": None,
                    "last_snapshot_mono": None,
                    "last_snapshot_at": None,
                    "cgroups": {},
                    "recent_comm": {},
                    "tracked_cgroups": [],
                }

        ebpf_status_global = ebpf_snapshot.get("status", "UNAVAILABLE")
        ebpf_reason_global = ebpf_snapshot.get("reason", "Unavailable")
        snap_mono = ebpf_snapshot.get("last_snapshot_mono")
        if ebpf_status_global == "OK":
            if snap_mono is None or (mono - snap_mono) > self.settings.stale_threshold_seconds:
                ebpf_status_global = "STALE"
                ebpf_reason_global = "eBPF snapshot exceeded freshness threshold"

        enriched_containers: dict[str, dict[str, Any]] = {}
        with self._lock:
            for sid in list(self._baselines):
                if sid not in active_ids:
                    self._baselines.pop(sid, None)
            for sid in list(self._history):
                if sid not in active_ids:
                    self._history.pop(sid, None)
            for sid in list(self._interactions):
                if sid not in {s.id for s in sessions}:
                    self._interactions.pop(sid, None)
            for cid in list(self._pid_cache):
                if cid not in active_cids:
                    self._pid_cache.pop(cid, None)

            for s in active_sessions:
                sid = s.id
                docker_sample = dict((container_samples or {}).get(sid) or {})
                cg = cgroup_samples.get(sid)
                cgid = cg["cgroup_id"] if cg else None
                base = self._baselines.get(sid)
                if base is not None and base.get("cgroup_id") != cgid:
                    base = None

                missing: list[str] = []
                cpu_pct: Optional[float] = None
                memory_bytes: Optional[int] = None
                psi_cpu = cg.get("psi_cpu_some_avg10") if cg else None
                psi_io = cg.get("psi_io_some_avg10") if cg else None

                if cg is not None:
                    memory_bytes = cg["memory_bytes"]
                    if base is not None and base.get("cg") is not None:
                        prev_cg = base["cg"]
                        dt_ns = cg["mono_ns"] - prev_cg["mono_ns"]
                        d_usage = cg["usage_ns"] - prev_cg["usage_ns"]
                        ratio = cg.get("quota_ratio") or (s.cpu_millis / 1000.0)
                        if dt_ns > 0 and d_usage >= 0 and ratio > 0:
                            cpu_pct = min(100.0, max(0.0, (d_usage / (dt_ns * ratio)) * 100.0))
                elif docker_sample.get("available"):
                    memory_bytes = docker_sample.get("memory_usage_bytes")
                    if base is not None and base.get("docker_cpu_ns") is not None and docker_sample.get("cpu_usage_ns") is not None:
                        dt_s = mono - base["mono"]
                        d_usage = docker_sample["cpu_usage_ns"] - base["docker_cpu_ns"]
                        ratio = s.cpu_millis / 1000.0
                        if dt_s > 0 and d_usage >= 0 and ratio > 0:
                            cpu_pct = min(100.0, max(0.0, (d_usage / (dt_s * 1_000_000_000.0 * ratio)) * 100.0))
                else:
                    missing.append("cgroup_and_docker_stats")

                ebpf_row = ebpf_snapshot["cgroups"].get(cgid) if cgid is not None else None
                loss_total = ebpf_snapshot.get("loss_count")
                loss_delta: Optional[int] = None
                session_ebpf_status = ebpf_status_global
                session_ebpf_reason = ebpf_reason_global

                io_read_delta = io_write_delta = io_events_delta = None
                sock_rx_delta = sock_tx_delta = sock_events_delta = None
                exec_delta = fork_delta = exit_delta = None
                io_read_bps = io_write_bps = sock_rx_bps = sock_tx_bps = None

                if cgid is None:
                    session_ebpf_status = "UNAVAILABLE"
                    session_ebpf_reason = "Container cgroup_id unavailable"
                    missing.append("cgroup_mapping")
                elif ebpf_status_global != "OK":
                    missing.append("ebpf_collector")
                elif ebpf_row is None:
                    session_ebpf_status = "DEGRADED"
                    session_ebpf_reason = "Awaiting first eBPF window for container cgroup"
                    missing.append("ebpf_window_baseline")
                else:
                    if base is not None and base.get("ebpf") is not None:
                        prev_e = base["ebpf"]
                        prev_ebpf_mono = base.get("ebpf_snap_mono")
                        if snap_mono is not None and prev_ebpf_mono is not None and snap_mono == prev_ebpf_mono and base.get("last_ebpf_deltas") is not None:
                            # Same kernel snapshot window: reuse previous deltas instead of reporting false zeros.
                            prev_d = base["last_ebpf_deltas"]
                            loss_delta = prev_d["loss_delta"]
                            io_read_delta = prev_d["io_read_delta"]
                            io_write_delta = prev_d["io_write_delta"]
                            io_events_delta = prev_d["io_events_delta"]
                            sock_rx_delta = prev_d["sock_rx_delta"]
                            sock_tx_delta = prev_d["sock_tx_delta"]
                            sock_events_delta = prev_d["sock_events_delta"]
                            exec_delta = prev_d["exec_delta"]
                            fork_delta = prev_d["fork_delta"]
                            exit_delta = prev_d["exit_delta"]
                            io_read_bps = prev_d["io_read_bps"]
                            io_write_bps = prev_d["io_write_bps"]
                            sock_rx_bps = prev_d["sock_rx_bps"]
                            sock_tx_bps = prev_d["sock_tx_bps"]
                        else:
                            dt_s = max(0.001, (snap_mono - prev_ebpf_mono) if (snap_mono is not None and prev_ebpf_mono is not None and snap_mono > prev_ebpf_mono) else (mono - base["mono"]))
                            if base.get("loss") is not None and loss_total is not None and loss_total >= base["loss"]:
                                loss_delta = loss_total - base["loss"]
                            io_read_delta = max(0, ebpf_row["io_read_bytes"] - prev_e["io_read_bytes"])
                            io_write_delta = max(0, ebpf_row["io_write_bytes"] - prev_e["io_write_bytes"])
                            io_events_delta = max(0, ebpf_row["io_events"] - prev_e["io_events"])
                            sock_rx_delta = max(0, ebpf_row["sock_rx_bytes"] - prev_e["sock_rx_bytes"])
                            sock_tx_delta = max(0, ebpf_row["sock_tx_bytes"] - prev_e["sock_tx_bytes"])
                            sock_events_delta = max(0, ebpf_row["socket_events"] - prev_e["socket_events"])
                            exec_delta = max(0, ebpf_row["exec"] - prev_e["exec"])
                            fork_delta = max(0, ebpf_row["fork"] - prev_e["fork"])
                            exit_delta = max(0, ebpf_row["exit"] - prev_e["exit"])
                            io_read_bps = io_read_delta / dt_s
                            io_write_bps = io_write_delta / dt_s
                            sock_rx_bps = sock_rx_delta / dt_s
                            sock_tx_bps = sock_tx_delta / dt_s
                        if loss_delta and loss_delta > 0:
                            session_ebpf_status = "DEGRADED"
                            session_ebpf_reason = f"eBPF ring buffer lost {loss_delta} exec event(s)"
                            missing.append("ebpf_ringbuf_loss")
                    else:
                        session_ebpf_status = "DEGRADED"
                        session_ebpf_reason = "Collecting eBPF baseline delta"
                        missing.append("ebpf_delta_baseline")

                interaction = self._interactions.get(sid)
                interaction_age = (mono - interaction[0]) if interaction is not None else None
                last_interaction_at = interaction[1] if interaction is not None else None
                last_interaction_source = interaction[2] if interaction is not None else None

                freshness_seconds = (mono - snap_mono) if snap_mono is not None else None
                if cpu_pct is None and "cpu_delta_baseline" not in missing:
                    missing.append("cpu_delta_baseline")

                if not missing and session_ebpf_status == "OK":
                    quality_status = "OK"
                    quality_reason = "All cgroup v2 and eBPF signals active and fresh"
                elif session_ebpf_status == "STALE":
                    quality_status = "STALE"
                    quality_reason = session_ebpf_reason
                elif cpu_pct is not None or memory_bytes is not None:
                    quality_status = "DEGRADED"
                    quality_reason = session_ebpf_reason
                else:
                    quality_status = "UNAVAILABLE"
                    quality_reason = session_ebpf_reason

                quiet_since = base.get("quiet_since") if base is not None else None
                quiet_seconds = 0.0
                if quality_status != "OK" or cpu_pct is None or io_events_delta is None or sock_events_delta is None or exec_delta is None:
                    quiet_since = None
                    rec_decision = "UNKNOWN"
                    rec_confidence = "NONE"
                    rec_reason = f"Abstaining (read-only): {quality_reason}"
                else:
                    active_reasons: list[str] = []
                    if cpu_pct >= self.settings.idle_cpu_threshold_pct:
                        active_reasons.append(f"CPU {cpu_pct:.1f}%")
                    if io_events_delta > 0:
                        active_reasons.append(f"VFS I/O {io_events_delta} ops ({(io_read_delta + io_write_delta) / 1024:.1f} KiB)")
                    if (psi_io or 0.0) >= 0.5:
                        active_reasons.append(f"I/O PSI {psi_io:.2f}")
                    if sock_events_delta > 0:
                        active_reasons.append(f"Socket {sock_events_delta} ops ({(sock_rx_delta + sock_tx_delta)} B)")
                    if exec_delta > 0 or (fork_delta or 0) > 0:
                        comm = ebpf_snapshot["recent_comm"].get(cgid) if cgid is not None else None
                        label = f"Process exec/fork ({exec_delta}/{fork_delta}" + (f", last={comm})" if comm else ")")
                        active_reasons.append(label)

                    if active_reasons:
                        quiet_since = None
                        rec_decision = "ACTIVE"
                        rec_confidence = "HIGH"
                        rec_reason = "Active workload: " + ", ".join(active_reasons)
                    else:
                        if quiet_since is None:
                            quiet_since = mono
                        quiet_seconds = mono - quiet_since
                        if interaction_age is not None and interaction_age < self.settings.interaction_grace_seconds:
                            rec_decision = "ACTIVE"
                            rec_confidence = "MEDIUM"
                            rec_reason = (
                                f"Recent {last_interaction_source or 'user'} interaction {interaction_age:.1f}s ago "
                                f"(grace {self.settings.interaction_grace_seconds:.0f}s; resources quiet {quiet_seconds:.1f}s)"
                            )
                        elif quiet_seconds >= self.settings.idle_quiet_seconds:
                            rec_decision = "IDLE_CANDIDATE"
                            rec_confidence = "HIGH"
                            age_note = f"last interaction {interaction_age:.1f}s ago" if interaction_age is not None else "no interaction recorded"
                            rec_reason = (
                                f"CPU ({cpu_pct:.1f}%), VFS I/O (0), socket (0), and eBPF exec/fork (0) quiet for "
                                f"{quiet_seconds:.1f}s; {age_note}"
                            )
                        else:
                            rec_decision = "ACTIVE"
                            rec_confidence = "MEDIUM"
                            rec_reason = f"Signals quiet for {quiet_seconds:.1f}s / {self.settings.idle_quiet_seconds:.0f}s threshold"

                self._baselines[sid] = {
                    "mono": mono,
                    "cgroup_id": cgid,
                    "cg": cg,
                    "docker_cpu_ns": docker_sample.get("cpu_usage_ns"),
                    "ebpf": ebpf_row,
                    "ebpf_snap_mono": snap_mono,
                    "last_ebpf_deltas": {
                        "loss_delta": loss_delta,
                        "io_read_delta": io_read_delta,
                        "io_write_delta": io_write_delta,
                        "io_events_delta": io_events_delta,
                        "sock_rx_delta": sock_rx_delta,
                        "sock_tx_delta": sock_tx_delta,
                        "sock_events_delta": sock_events_delta,
                        "exec_delta": exec_delta,
                        "fork_delta": fork_delta,
                        "exit_delta": exit_delta,
                        "io_read_bps": io_read_bps,
                        "io_write_bps": io_write_bps,
                        "sock_rx_bps": sock_rx_bps,
                        "sock_tx_bps": sock_tx_bps,
                    } if io_events_delta is not None else None,
                    "loss": loss_total,
                    "quiet_since": quiet_since,
                }

                history_buf = self._history.setdefault(sid, deque(maxlen=HISTORY_LIMIT))
                history_buf.append({
                    "sampled_at": iso,
                    "cpu_pct": round(cpu_pct, 2) if cpu_pct is not None else None,
                    "memory_bytes": memory_bytes,
                    "io_events": io_events_delta,
                    "socket_events": sock_events_delta,
                    "exec_events": exec_delta,
                    "decision": rec_decision,
                })

                enriched = dict(docker_sample)
                if "available" not in enriched:
                    enriched["available"] = cg is not None
                if "sampled_at" not in enriched:
                    enriched["sampled_at"] = iso
                if memory_bytes is not None and enriched.get("memory_usage_bytes") is None:
                    enriched["memory_usage_bytes"] = memory_bytes
                enriched["signals"] = {
                    "cgroup_id": cgid,
                    "cpu_pct": round(cpu_pct, 2) if cpu_pct is not None else None,
                    "memory_bytes": memory_bytes,
                    "blk_read_bytes": cg["blk_read_bytes"] if cg else None,
                    "blk_write_bytes": cg["blk_write_bytes"] if cg else None,
                    "io_read_bytes_total": ebpf_row["io_read_bytes"] if ebpf_row else None,
                    "io_write_bytes_total": ebpf_row["io_write_bytes"] if ebpf_row else None,
                    "io_read_bytes_per_sec": round(io_read_bps, 1) if io_read_bps is not None else None,
                    "io_write_bytes_per_sec": round(io_write_bps, 1) if io_write_bps is not None else None,
                    "io_events_delta": io_events_delta,
                    "sock_rx_bytes_total": ebpf_row["sock_rx_bytes"] if ebpf_row else None,
                    "sock_tx_bytes_total": ebpf_row["sock_tx_bytes"] if ebpf_row else None,
                    "sock_rx_bytes_per_sec": round(sock_rx_bps, 1) if sock_rx_bps is not None else None,
                    "sock_tx_bytes_per_sec": round(sock_tx_bps, 1) if sock_tx_bps is not None else None,
                    "socket_events_delta": sock_events_delta,
                    "exec_events_delta": exec_delta,
                    "fork_events_delta": fork_delta,
                    "exit_events_delta": exit_delta,
                    "recent_comm": ebpf_snapshot["recent_comm"].get(cgid) if cgid is not None else None,
                    "psi_cpu_some_avg10": psi_cpu,
                    "psi_io_some_avg10": psi_io,
                    "last_interaction_at": last_interaction_at,
                    "last_interaction_source": last_interaction_source,
                    "interaction_age_seconds": round(interaction_age, 1) if interaction_age is not None else None,
                    "sample_time": iso,
                }
                enriched["signal_quality"] = {
                    "status": quality_status,
                    "ebpf_status": session_ebpf_status,
                    "freshness_seconds": round(freshness_seconds, 2) if freshness_seconds is not None else None,
                    "loss_delta": loss_delta,
                    "missing": missing,
                    "reason": quality_reason,
                }
                enriched["recommendation"] = {
                    "decision": rec_decision,
                    "confidence": rec_confidence,
                    "quiet_seconds": round(quiet_seconds, 1),
                    "reason": rec_reason,
                    "read_only": True,
                }
                enriched["history"] = list(history_buf)
                enriched_containers[sid] = enriched

            for sid, sample in (container_samples or {}).items():
                if sid not in enriched_containers:
                    enriched_containers[sid] = dict(sample)

        return {
            "containers": enriched_containers,
            "observability": {
                "read_only": True,
                "ebpf": {
                    "enabled": self.settings.enable_ebpf,
                    "status": ebpf_status_global,
                    "reason": ebpf_reason_global,
                    "probes": ebpf_snapshot.get("probes", []),
                    "loss_count": ebpf_snapshot.get("loss_count"),
                    "last_snapshot_at": ebpf_snapshot.get("last_snapshot_at"),
                    "tracked_cgroups": ebpf_snapshot.get("tracked_cgroups", []),
                },
                "thresholds": {
                    "idle_cpu_threshold_pct": self.settings.idle_cpu_threshold_pct,
                    "idle_quiet_seconds": self.settings.idle_quiet_seconds,
                    "interaction_grace_seconds": self.settings.interaction_grace_seconds,
                    "stale_threshold_seconds": self.settings.stale_threshold_seconds,
                },
            },
        }
