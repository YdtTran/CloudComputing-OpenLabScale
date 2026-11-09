from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from time import monotonic
from typing import Optional
from uuid import uuid4

from .models import LifecycleEvent, Request, Session, Settings, State, now

log = logging.getLogger(__name__)
TERMINAL = {State.COMPLETED, State.CANCELLED, State.RELEASED, State.FAILED}
TRANSITIONS = {
    State.REQUESTED: {State.QUEUED},
    State.QUEUED: {State.PROVISIONING, State.CANCELLED, State.FAILED},
    State.PROVISIONING: {State.RUNNING, State.RELEASING},
    State.RUNNING: {State.RELEASING},
    State.RELEASING: TERMINAL,
}


@dataclass
class Entry:
    session: Session
    changed_at: float = field(default_factory=monotonic)
    final: Optional[State] = None
    terminal_closed: asyncio.Event = field(default_factory=asyncio.Event)
    terminal_attached: bool = False

    def transition(self, target: State) -> None:
        state = self.session.state
        assert target in TRANSITIONS[state]
        elapsed = monotonic() - self.changed_at
        if state == State.QUEUED:
            self.session.queue_seconds = elapsed
        if state == State.PROVISIONING:
            self.session.provisioning_seconds = elapsed
        self.changed_at = monotonic()
        self.session.state = target
        self.session.events.append(LifecycleEvent(state=target, at=now()))


class Scheduler:
    """All ledger mutations run on the API event loop without yielding."""

    def __init__(self, settings: Settings, docker):
        self.settings = settings
        self.docker = docker
        self.sessions: dict[str, Entry] = {}
        self.queue: deque[str] = deque()
        self.reserved: dict[str, Entry] = {}
        self.wake = asyncio.Event()
        self.stopping = False
        self.healthy = True

    def submit(self, owner: str, request: Request) -> Session:
        cpu = request.cpu_millis or self.settings.default_cpu_millis
        memory = request.memory_mib or self.settings.default_memory_mib
        if cpu > self.settings.cpu_budget or memory > self.settings.memory_budget:
            raise ValueError("request exceeds the schedulable budget")
        session = Session(id=uuid4().hex, owner=owner, cpu_millis=cpu, memory_mib=memory)
        session.events.append(LifecycleEvent(state=session.state, at=session.created_at))
        entry = Entry(session)
        entry.transition(State.QUEUED)
        self.sessions[session.id] = entry
        self.queue.append(session.id)
        self.wake.set()
        return self.snapshot(entry)

    def snapshot(self, entry: Entry) -> Session:
        session = entry.session.model_copy(deep=True)
        if session.state == State.QUEUED:
            session.queue_position = self.queue.index(session.id) + 1
            session.queue_seconds = monotonic() - entry.changed_at
        return session

    def release(self, entry: Entry) -> None:
        state = entry.session.state
        if state == State.QUEUED:
            self.queue.remove(entry.session.id)
            entry.transition(State.CANCELLED)
        elif state == State.PROVISIONING and entry.final is None:
            entry.final = State.CANCELLED
        elif state == State.RUNNING:
            self.begin_cleanup(entry, State.RELEASED)
        self.wake.set()

    def begin_cleanup(self, entry: Entry, final: State) -> None:
        entry.final = final
        entry.terminal_closed.set()
        entry.session.cleanup_pending = True
        entry.transition(State.RELEASING)

    def capacity(self) -> dict:
        budget = dict(cpu_millis=self.settings.cpu_budget, memory_mib=self.settings.memory_budget,
                      slots=self.settings.max_sessions)
        used = dict(cpu_millis=sum(e.session.cpu_millis for e in self.reserved.values()),
                    memory_mib=sum(e.session.memory_mib for e in self.reserved.values()),
                    slots=len(self.reserved))
        return {"budget": budget, "reserved": used,
                "available": {key: budget[key] - used[key] for key in budget}}

    def admit(self) -> Optional[Entry]:
        if not self.queue or self.stopping or not self.healthy:
            return None
        entry = self.sessions[self.queue[0]]
        session = entry.session
        available = self.capacity()["available"]
        owned = sum(e.session.owner == session.owner for e in self.reserved.values())
        if (available["slots"] < 1 or available["cpu_millis"] < session.cpu_millis
                or available["memory_mib"] < session.memory_mib or owned >= self.settings.per_user):
            return None
        self.queue.popleft()
        self.reserved[session.id] = entry
        entry.transition(State.PROVISIONING)
        return entry

    async def provision(self, entry: Entry) -> None:
        try:
            entry.session.container_id = await asyncio.to_thread(self.docker.provision, entry.session)
        except Exception:
            log.exception("Provisioning failed for %s", entry.session.id)
            entry.session.failure = "Docker provisioning failed"
            self.begin_cleanup(entry, entry.final or State.FAILED)
        else:
            if entry.final:
                self.begin_cleanup(entry, entry.final)
            else:
                entry.transition(State.RUNNING)

    async def maintain(self) -> None:
        try:
            await asyncio.to_thread(self.docker.reap_orphans, set(self.reserved))
        except Exception:
            log.exception("Docker inventory or orphan cleanup failed")
            self.healthy = False
        else:
            self.healthy = True
        for sid in list(self.queue):
            entry = self.sessions[sid]
            if monotonic() - entry.changed_at >= self.settings.queue_seconds:
                self.queue.remove(sid)
                entry.session.failure = "Queue deadline exceeded"
                entry.transition(State.FAILED)
        for sid, entry in list(self.reserved.items()):
            if entry.session.state == State.RUNNING:
                if monotonic() - entry.changed_at >= self.settings.lifetime_seconds:
                    self.begin_cleanup(entry, State.COMPLETED)
                else:
                    try:
                        status = await asyncio.to_thread(self.docker.status, entry.session)
                    except Exception:
                        log.exception("Inspection failed for %s", sid)
                        self.healthy = False
                    else:
                        if status != "running" and entry.session.state == State.RUNNING:
                            if status == "completed":
                                self.begin_cleanup(entry, State.COMPLETED)
                            else:
                                entry.session.failure = "Container stopped unexpectedly"
                                self.begin_cleanup(entry, State.FAILED)
        for sid, entry in list(self.reserved.items()):
            if entry.session.state == State.RELEASING:
                try:
                    await asyncio.to_thread(self.docker.remove, entry.session)
                except Exception:
                    log.exception("Cleanup pending for %s", sid)
                    continue
                entry.session.cleanup_pending = False
                assert entry.final is not None
                entry.transition(entry.final)
                del self.reserved[sid]

    async def run(self) -> None:
        while not self.stopping:
            self.wake.clear()
            await self.maintain()
            entry = self.admit()
            if entry:
                await self.provision(entry)
                continue
            try:
                await asyncio.wait_for(self.wake.wait(), self.settings.poll_seconds)
            except asyncio.TimeoutError:
                pass
        for entry in list(self.sessions.values()):
            self.release(entry)
        await self.maintain()
        if self.reserved:
            log.error("Shutdown left pending cleanup for %s", list(self.reserved))
