from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

import docker
from docker.errors import APIError, NotFound

from .models import Session, Settings, now

log = logging.getLogger(__name__)
LABEL = "openlabscale.deployment"
SESSION_LABEL = "openlabscale.session"


def host_counters() -> dict:
    try:
        cpu = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:9]))
        memory = {line.split(":")[0]: int(line.split()[1]) * 1024
                  for line in Path("/proc/meminfo").read_text().splitlines()
                  if line.startswith(("MemTotal:", "MemAvailable:"))}
        return {"available": True, "cpu_total_ticks": sum(cpu), "cpu_idle_ticks": cpu[3] + cpu[4],
                "memory_total_bytes": memory["MemTotal"],
                "memory_used_bytes": memory["MemTotal"] - memory["MemAvailable"],
                "sampled_at": now()}
    except (OSError, ValueError, IndexError, KeyError):
        return {"available": False}


class Engine:
    def __init__(self, settings: Settings, client=None, pending: Optional[Path] = None):
        self.settings = settings
        self.client = client if client is not None else docker.from_env(timeout=settings.docker_timeout_seconds)
        self.pending = pending
        self.uncertain_creates = {path.stem for path in pending.glob("*.create")} if pending else set()
        self.image = settings.image

    def name(self, session: Session) -> str:
        return f"openlabscale-{self.settings.deployment}-{session.id}"

    def owned(self) -> list:
        containers = self.client.containers.list(all=True, filters={
            "label": [f"{LABEL}={self.settings.deployment}", SESSION_LABEL],
        })
        return [container for container in containers if
                container.labels.get(LABEL) == self.settings.deployment and container.labels.get(SESSION_LABEL)]

    def forget_create(self, session_id: str) -> None:
        if session_id in self.uncertain_creates:
            if self.pending:
                (self.pending / f"{session_id}.create").unlink(missing_ok=True)
            self.uncertain_creates.remove(session_id)

    def reap_orphans(self, reserved: set[str]) -> None:
        for container in self.owned():
            session_id = container.labels[SESSION_LABEL]
            if session_id not in reserved:
                self.forget_create(session_id)
                self.delete(container)

    def reconcile(self) -> None:
        self.client.ping()
        self.reap_orphans(set())
        if self.owned():
            raise RuntimeError("Could not verify removal of deployment containers")
        if self.uncertain_creates:
            raise RuntimeError(f"Unresolved Docker create markers: {sorted(self.uncertain_creates)}")

    def check_runtime(self) -> None:
        info = self.client.info()
        required = ("MemoryLimit", "SwapLimit", "CpuCfsPeriod", "CpuCfsQuota", "PidsLimit")
        if info.get("OSType") != "linux" or not all(info.get(key) for key in required):
            raise RuntimeError("Docker must support Linux CPU, memory, swap and PID limits")
        if (self.settings.host_cpu_millis > info["NCPU"] * 1000
                or self.settings.host_memory_mib * 1024**2 > info["MemTotal"]):
            raise RuntimeError("Configured host capacity exceeds Docker host CPU or memory")
        image = self.client.images.get(self.settings.image)
        if image.attrs["Config"].get("Volumes"):
            raise RuntimeError("Workspace image must not declare volumes")
        self.image = image.id

    def get(self, session: Session):
        container = self.client.containers.get(self.name(session))
        if (container.labels.get(LABEL) != self.settings.deployment
                or container.labels.get(SESSION_LABEL) != session.id):
            raise RuntimeError("Docker name matched a container with different ownership labels")
        return container

    def provision(self, session: Session) -> str:
        if self.pending:
            (self.pending / f"{session.id}.create").touch(exist_ok=False)
        self.uncertain_creates.add(session.id)
        try:
            container = self.client.containers.create(
                self.image, ["/bin/sleep", str(self.settings.lifetime_seconds)],
                entrypoint=[""], name=self.name(session),
                labels={LABEL: self.settings.deployment, SESSION_LABEL: session.id},
                nano_cpus=session.cpu_millis * 1_000_000,
                mem_limit=session.memory_mib * 1024**2, memswap_limit=session.memory_mib * 1024**2,
                pids_limit=self.settings.pids, user="65534:65534", privileged=False,
                cap_drop=["ALL"], security_opt=["no-new-privileges:true"], network_mode="none",
                read_only=True, tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=16m,mode=1777"},
                init=True, restart_policy={"Name": "no"},
            )
        except APIError as error:
            if error.status_code is not None and 400 <= error.status_code < 500 and error.status_code != 408:
                self.forget_create(session.id)
            raise
        self.forget_create(session.id)
        container.start()
        container.reload()
        if container.status != "running":
            raise RuntimeError(f"Container did not start: {container.status}")
        return container.id

    def status(self, session: Session) -> str:
        try:
            container = self.get(session)
        except NotFound:
            return "missing"
        if container.status == "exited" and container.attrs["State"]["ExitCode"] == 0:
            return "completed"
        return container.status

    @staticmethod
    def delete(container) -> None:
        try:
            container.remove(force=True)
        except NotFound:
            pass

    def remove(self, session: Session) -> None:
        try:
            container = self.get(session)
        except NotFound:
            if session.id in self.uncertain_creates:
                raise RuntimeError("Docker create outcome remains unknown")
        else:
            self.forget_create(session.id)
            self.delete(container)

    def telemetry(self) -> dict:
        host = host_counters()
        try:
            containers = self.owned()
        except Exception:
            log.exception("Container inventory unavailable")
            return {"host": host, "active_containers": None, "containers": None}
        samples = {}
        for container in containers:
            if container.status != "running":
                continue
            sample = {"available": False, "sampled_at": now()}
            try:
                data = container.stats(stream=False, one_shot=True)
                cpu = data.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage")
                memory = data.get("memory_stats", {}).get("usage")
                sample = {"available": cpu is not None or memory is not None, "cpu_usage_ns": cpu,
                          "memory_usage_bytes": memory, "sampled_at": data.get("read") or now()}
            except Exception:
                log.exception("Metrics unavailable for %s", container.id)
            samples[container.labels[SESSION_LABEL]] = sample
        return {"host": host, "active_containers": len(samples), "containers": samples}

    def open_terminal(self, session: Session):
        api = self.client.api
        marker = uuid4().hex
        pid_file = f"/tmp/.openlabscale-pty-{marker}"
        terminal = api.exec_create(
            session.container_id,
            ["/bin/sh", "-c", 'umask 077; echo "$$" > "$1" && printf "R" && exec /bin/sh -i', "terminal", pid_file],
            stdin=True, tty=True, user="65534:65534", environment={"OPENLABSCALE_PTY": marker},
        )["Id"]
        try:
            stream = api.exec_start(terminal, tty=True, socket=True)
            # Read readiness through HTTP's buffer before taking over the Unix socket.
            sock = stream._sock
            response = stream._response
            try:
                reader = response.raw._fp.fp
                sock.settimeout(self.settings.docker_timeout_seconds)
                if reader.read1(1) != b"R":
                    raise RuntimeError("Terminal did not initialize")
                sock.setblocking(False)
                initial = reader.read1(65536)
                connection = sock.dup()
            finally:
                response.close()
                sock.close()
        except Exception:
            self.close_terminal(session, marker)
            raise
        return terminal, marker, connection, initial

    def close_terminal(self, session: Session, marker: str) -> None:
        # Detaching Docker's socket alone can leave the interactive shell running.
        script = r'''file="/tmp/.openlabscale-pty-$1"
pid=$(cat "$file" 2>/dev/null)
case "$pid" in
    ''|*[!0-9]*) exit 0 ;;
esac
if tr '\000' '\n' < "/proc/$pid/environ" | grep -Fxq "OPENLABSCALE_PTY=$1"; then
    kill -KILL "$pid"
fi
rm -f "$file"'''
        try:
            container = self.get(session)
            if container.status == "running":
                container.exec_run(["/bin/sh", "-c", script, "cleanup", marker], user="65534:65534")
        except NotFound:
            pass

    def resize(self, terminal: str, rows: int, cols: int) -> None:
        self.client.api.exec_resize(terminal, height=rows, width=cols)
