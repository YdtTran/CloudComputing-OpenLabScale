import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Cpu,
  Database,
  Layers,
  Lock,
  Pause,
  Play,
  RefreshCw,
  Server,
  ShieldAlert,
} from 'lucide-react';
import { getStats } from '../api';
import type { AdminStats, ContainerSample, Session, SessionState } from '../types';

const STALE_THRESHOLD_MS = 8000;
const MAX_HISTORY = 30;

interface HistoryPoint {
  sampledAt: string;
  running: number;
  queued: number;
  provisioning: number;
  hostCpuPct: number | null;
  hostMemPct: number | null;
  reservedCpuPct: number;
  reservedMemPct: number;
}

interface PrevContainerCpu {
  cpuNs: number;
  sampledAtMs: number;
}

interface AdminDashboardProps {
  token: string;
  identityLabel: string;
  onSelectAdmin: () => void;
}

function formatBytesToMib(bytes?: number | null): string {
  if (bytes == null || Number.isNaN(bytes)) return 'UNAVAILABLE';
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function formatUtcTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace('T', ' ').slice(11, 23) + ' UTC';
}

function isSampleStale(isoTimestamp: string | undefined | null, nowMs: number): boolean {
  if (!isoTimestamp) return true;
  const parsed = new Date(isoTimestamp).getTime();
  if (Number.isNaN(parsed)) return true;
  return nowMs - parsed > STALE_THRESHOLD_MS;
}

function sampleAgeSeconds(isoTimestamp: string | undefined | null, nowMs: number): string {
  if (!isoTimestamp) return 'unknown age';
  const parsed = new Date(isoTimestamp).getTime();
  if (Number.isNaN(parsed)) return 'unknown age';
  const sec = Math.max(0, (nowMs - parsed) / 1000);
  return `${sec.toFixed(1)}s ago`;
}

export function AdminDashboard({ token, identityLabel, onSelectAdmin }: AdminDashboardProps) {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [authDenied, setAuthDenied] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [autoPoll, setAutoPoll] = useState<boolean>(true);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [containerCpuRates, setContainerCpuRates] = useState<Record<string, number | null>>({});
  const prevContainerCpuRef = useRef<Record<string, PrevContainerCpu>>({});

  const fetchSnapshot = useCallback(async () => {
    if (!token) {
      setAuthDenied('HTTP 401: Valid demo bearer token required');
      return;
    }
    setLoading(true);
    try {
      const data = await getStats(token);
      setAuthDenied(null);
      setPollError(null);
      setStats(data);
      setNowMs(Date.now());

      // Compute per-container CPU % delta when consecutive samples exist
      if (data.containers) {
        const nextRates: Record<string, number | null> = {};
        const nextPrev: Record<string, PrevContainerCpu> = {};
        for (const [sid, sample] of Object.entries(data.containers)) {
          const tsMs = new Date(sample.sampled_at).getTime();
          if (sample.available && sample.cpu_usage_ns != null && !Number.isNaN(tsMs)) {
            const prev = prevContainerCpuRef.current[sid];
            if (prev && tsMs > prev.sampledAtMs && sample.cpu_usage_ns >= prev.cpuNs) {
              const deltaCpuNs = sample.cpu_usage_ns - prev.cpuNs;
              const deltaWallNs = (tsMs - prev.sampledAtMs) * 1_000_000;
              nextRates[sid] = (deltaCpuNs / deltaWallNs) * 100;
            } else {
              nextRates[sid] = null;
            }
            nextPrev[sid] = { cpuNs: sample.cpu_usage_ns, sampledAtMs: tsMs };
          } else {
            nextRates[sid] = null;
          }
        }
        prevContainerCpuRef.current = nextPrev;
        setContainerCpuRates(nextRates);
      }

      const hostMemPct =
        data.host.available &&
        data.host.memory_used_bytes != null &&
        data.host.memory_total_bytes != null &&
        data.host.memory_total_bytes > 0
          ? (data.host.memory_used_bytes / data.host.memory_total_bytes) * 100
          : null;

      const point: HistoryPoint = {
        sampledAt: data.sampled_at,
        running: data.counts.RUNNING ?? 0,
        queued: data.counts.QUEUED ?? 0,
        provisioning: data.counts.PROVISIONING ?? 0,
        hostCpuPct: data.host.available ? (data.host.cpu_utilization_pct ?? null) : null,
        hostMemPct,
        reservedCpuPct:
          data.budget.cpu_millis > 0 ? (data.reserved.cpu_millis / data.budget.cpu_millis) * 100 : 0,
        reservedMemPct:
          data.budget.memory_mib > 0 ? (data.reserved.memory_mib / data.budget.memory_mib) * 100 : 0,
      };
      setHistory((prev) => [...prev.slice(-(MAX_HISTORY - 1)), point]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch /stats';
      if (msg.includes('401') || msg.includes('403')) {
        setAuthDenied(msg);
      } else {
        setPollError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchSnapshot();
  }, [fetchSnapshot]);

  useEffect(() => {
    if (!autoPoll || authDenied) return;
    const timer = setInterval(fetchSnapshot, 2000);
    return () => clearInterval(timer);
  }, [autoPoll, authDenied, fetchSnapshot]);

  useEffect(() => {
    const ticker = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(ticker);
  }, []);

  if (authDenied) {
    return (
      <div className="bg-slate-900 border border-rose-500/40 rounded-xl p-8 flex flex-col items-center justify-center text-center my-4">
        <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-full text-rose-400 mb-4">
          <Lock className="w-8 h-8" />
        </div>
        <h2 className="text-base font-bold text-white mb-2">
          Administrator Access Denied
        </h2>
        <p className="text-xs text-rose-300 font-mono mb-3 px-3 py-1.5 rounded bg-rose-950/60 border border-rose-500/30">
          GET /stats &rarr; {authDenied}
        </p>
        <p className="text-xs text-slate-400 max-w-lg mb-5">
          Current identity <span className="text-slate-200 font-semibold">{identityLabel}</span> is not authorized to read operational telemetry. The backend restricts <code className="text-sky-300">/stats</code> to the configured administrator identity and rejects student or unauthenticated tokens.
        </p>
        <button
          onClick={onSelectAdmin}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold rounded-lg transition cursor-pointer flex items-center gap-2"
        >
          <ShieldAlert className="w-4 h-4" />
          Switch to Operator (Admin) Identity
        </button>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 flex items-center justify-center gap-3 text-xs text-slate-400">
        <RefreshCw className="w-4 h-4 animate-spin text-sky-400" />
        Loading real telemetry snapshot from GET /stats...
      </div>
    );
  }

  const snapshotStale = Boolean(pollError) || isSampleStale(stats.sampled_at, nowMs);
  const hostStale = snapshotStale || (stats.host.available && isSampleStale(stats.host.sampled_at, nowMs));

  const hostMemPct =
    stats.host.available &&
    stats.host.memory_used_bytes != null &&
    stats.host.memory_total_bytes != null &&
    stats.host.memory_total_bytes > 0
      ? (stats.host.memory_used_bytes / stats.host.memory_total_bytes) * 100
      : null;

  const sessionMap = new Map<string, Session>(stats.sessions.map((s) => [s.id, s]));
  const queuedSessions = stats.queue.map((id, idx) => ({
    id,
    position: idx + 1,
    session: sessionMap.get(id),
  }));

  // Determine why queue head is waiting when queue is non-empty
  const headSession = queuedSessions[0]?.session;
  const headBlockingReasons: string[] = [];
  if (headSession) {
    if (stats.available.slots < 1) {
      headBlockingReasons.push(`Slot limit reached (${stats.reserved.slots}/${stats.budget.slots} slots)`);
    }
    if (stats.available.cpu_millis < headSession.cpu_millis) {
      headBlockingReasons.push(
        `Insufficient available CPU (${stats.available.cpu_millis} mCPU free < ${headSession.cpu_millis} mCPU requested)`,
      );
    }
    if (stats.available.memory_mib < headSession.memory_mib) {
      headBlockingReasons.push(
        `Insufficient available RAM (${stats.available.memory_mib} MiB free < ${headSession.memory_mib} MiB requested)`,
      );
    }
    const ownerActive = stats.sessions.filter(
      (s) =>
        s.owner === headSession.owner &&
        ['PROVISIONING', 'RUNNING', 'RELEASING'].includes(s.state),
    ).length;
    if (headBlockingReasons.length === 0 && ownerActive > 0) {
      headBlockingReasons.push(
        `Owner "${headSession.owner}" has ${ownerActive} active/reserved session(s) (per-user limit or provisioning in flight)`,
      );
    }
  }

  // Flatten all lifecycle events across sessions for operational audit feed
  const allEvents = stats.sessions
    .flatMap((s) =>
      s.events.map((ev, idx) => ({
        key: `${s.id}-${ev.state}-${idx}`,
        sessionId: s.id,
        owner: s.owner,
        state: ev.state,
        at: ev.at,
        cpuMillis: s.cpu_millis,
        memoryMib: s.memory_mib,
        queueSeconds: s.queue_seconds,
        provisioningSeconds: s.provisioning_seconds,
        failure: s.failure,
        cleanupPending: s.cleanup_pending,
      })),
    )
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());

  const sortedSessions = [...stats.sessions].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  const getStateBadge = (state: SessionState, queuePos?: number | null) => {
    switch (state) {
      case 'RUNNING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            RUNNING
          </span>
        );
      case 'PROVISIONING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/30">
            <RefreshCw className="w-3 h-3 animate-spin" />
            PROVISIONING
          </span>
        );
      case 'REQUESTED':
      case 'QUEUED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
            <Clock className="w-3 h-3" />
            {state} {queuePos ? `(#${queuePos})` : ''}
          </span>
        );
      case 'RELEASING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/30">
            <RefreshCw className="w-3 h-3 animate-spin" />
            RELEASING
          </span>
        );
      case 'RELEASED':
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            {state}
          </span>
        );
      case 'FAILED':
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <ShieldAlert className="w-3 h-3" />
            {state}
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Telemetry Source & Staleness Header Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-sky-500/10 text-sky-300 border border-sky-500/30">
            <Server className="w-3.5 h-3.5" />
            Live Single-Host Session Telemetry (GET /stats)
          </span>
          <span className="text-xs text-slate-400">
            Real Docker SDK + Linux <code className="text-slate-300">/proc</code> counters (distinct from offline <code className="text-slate-300">simulation/</code> &amp; <code className="text-slate-300">measured/</code> v1 bundles)
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          {snapshotStale ? (
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/40"
              title={`Snapshot timestamp: ${stats.sampled_at}`}
            >
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              STALE SNAPSHOT &mdash; sampled {formatUtcTime(stats.sampled_at)} ({sampleAgeSeconds(stats.sampled_at, nowMs)})
            </span>
          ) : (
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/30"
              title={`Snapshot timestamp: ${stats.sampled_at}`}
            >
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Sampled: {formatUtcTime(stats.sampled_at)} ({sampleAgeSeconds(stats.sampled_at, nowMs)})
            </span>
          )}

          <button
            onClick={() => setAutoPoll((p) => !p)}
            className={`px-2.5 py-1 rounded-md border font-medium flex items-center gap-1.5 cursor-pointer transition ${
              autoPoll
                ? 'bg-slate-800 border-slate-700 text-slate-200 hover:bg-slate-700'
                : 'bg-amber-500/15 border-amber-500/40 text-amber-300 hover:bg-amber-500/25'
            }`}
            title="Pause polling to verify stale indicator after 8s"
          >
            {autoPoll ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
            {autoPoll ? 'Polling (2s)' : 'Polling Paused'}
          </button>

          <button
            onClick={fetchSnapshot}
            disabled={loading}
            className="px-2.5 py-1 rounded-md bg-sky-600/20 hover:bg-sky-600/30 border border-sky-500/40 text-sky-300 font-medium flex items-center gap-1.5 cursor-pointer transition"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {pollError && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-200 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              Poll failed ({pollError}). Showing last retained snapshot from{' '}
              <span className="font-mono font-semibold">{formatUtcTime(stats.sampled_at)}</span> (marked STALE).
            </span>
          </div>
        </div>
      )}

      {/* Lifecycle Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">
            Total Requests
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-1">
            {stats.total_sessions}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            In-memory ledger sessions
          </div>
        </div>

        <div className="bg-slate-900 border border-emerald-500/30 rounded-xl p-4">
          <div className="text-[11px] uppercase tracking-wider text-emerald-400 font-semibold">
            Running
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400 mt-1 flex items-baseline gap-2">
            <span>{stats.counts.RUNNING ?? 0}</span>
            <span className="text-xs font-normal text-slate-400">
              / {stats.budget.slots} slots
            </span>
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Docker active:{' '}
            {stats.active_containers === null ? (
              <span className="text-amber-400 font-semibold">UNAVAILABLE</span>
            ) : (
              <span className="font-mono text-slate-200">{stats.active_containers}</span>
            )}
          </div>
        </div>

        <div className="bg-slate-900 border border-amber-500/30 rounded-xl p-4">
          <div className="text-[11px] uppercase tracking-wider text-amber-400 font-semibold">
            Queued (FIFO)
          </div>
          <div className="text-2xl font-bold font-mono text-amber-400 mt-1">
            {stats.counts.QUEUED ?? 0}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Queue length: <span className="font-mono text-slate-200">{stats.queue.length}</span>
            {stats.counts.REQUESTED ? ` (+${stats.counts.REQUESTED} req)` : ''}
          </div>
        </div>

        <div className="bg-slate-900 border border-sky-500/30 rounded-xl p-4">
          <div className="text-[11px] uppercase tracking-wider text-sky-400 font-semibold">
            Provisioning
          </div>
          <div className="text-2xl font-bold font-mono text-sky-400 mt-1">
            {stats.counts.PROVISIONING ?? 0}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Releasing: <span className="font-mono text-purple-300">{stats.counts.RELEASING ?? 0}</span>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] uppercase tracking-wider text-slate-300 font-semibold">
            Completed / Released
          </div>
          <div className="text-2xl font-bold font-mono text-slate-200 mt-1">
            {(stats.counts.COMPLETED ?? 0) + (stats.counts.RELEASED ?? 0)}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 font-mono">
            {stats.counts.COMPLETED ?? 0} done &middot; {stats.counts.RELEASED ?? 0} released
          </div>
        </div>

        <div className="bg-slate-900 border border-rose-500/30 rounded-xl p-4">
          <div className="text-[11px] uppercase tracking-wider text-rose-400 font-semibold">
            Failed / Cancelled
          </div>
          <div className="text-2xl font-bold font-mono text-rose-400 mt-1">
            {(stats.counts.FAILED ?? 0) + (stats.counts.CANCELLED ?? 0)}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 font-mono">
            {stats.counts.FAILED ?? 0} failed &middot; {stats.counts.CANCELLED ?? 0} cancelled
          </div>
        </div>
      </div>

      {/* Host Telemetry & Scheduler Capacity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Host Resource Use (/proc/stat & /proc/meminfo) */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-sky-400" />
              Host CPU &amp; Memory Telemetry (/proc)
            </h3>
            {!stats.host.available ? (
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
                UNAVAILABLE (sampled {formatUtcTime(stats.sampled_at)})
              </span>
            ) : hostStale ? (
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
                STALE ({formatUtcTime(stats.host.sampled_at)})
              </span>
            ) : (
              <span className="text-[11px] font-mono text-slate-400">
                Sampled {formatUtcTime(stats.host.sampled_at)}
              </span>
            )}
          </div>

          {!stats.host.available ? (
            <div className="p-4 rounded-lg bg-rose-950/30 border border-rose-500/30 text-xs text-rose-300">
              Host <code className="font-mono">/proc/stat</code> or <code className="font-mono">/proc/meminfo</code> is unavailable on this platform. No synthetic host values are invented.
            </div>
          ) : (
            <div className="space-y-4">
              {/* Host CPU */}
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-300 font-medium">Host CPU Utilization</span>
                  {stats.host.cpu_utilization_pct == null ? (
                    <span className="font-mono text-amber-300 text-[11px] px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/30">
                      UNAVAILABLE (1st sample &mdash; awaiting tick delta @ {formatUtcTime(stats.host.sampled_at)})
                    </span>
                  ) : (
                    <span className="font-mono font-semibold text-sky-400">
                      {stats.host.cpu_utilization_pct.toFixed(1)}%
                    </span>
                  )}
                </div>
                <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-sky-500 transition-all duration-300"
                    style={{
                      width: `${Math.min(100, Math.max(0, stats.host.cpu_utilization_pct ?? 0))}%`,
                    }}
                  />
                </div>
                <div className="flex justify-between text-[11px] text-slate-500 mt-1 font-mono">
                  <span>total_ticks: {stats.host.cpu_total_ticks ?? '—'}</span>
                  <span>idle_ticks: {stats.host.cpu_idle_ticks ?? '—'}</span>
                </div>
              </div>

              {/* Host Memory */}
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-300 font-medium">Host Memory Usage</span>
                  {hostMemPct == null ? (
                    <span className="font-mono text-amber-300 text-[11px]">
                      UNAVAILABLE ({formatUtcTime(stats.host.sampled_at)})
                    </span>
                  ) : (
                    <span className="font-mono font-semibold text-purple-400">
                      {formatBytesToMib(stats.host.memory_used_bytes)} /{' '}
                      {formatBytesToMib(stats.host.memory_total_bytes)} ({hostMemPct.toFixed(1)}%)
                    </span>
                  )}
                </div>
                <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-purple-500 transition-all duration-300"
                    style={{
                      width: `${Math.min(100, Math.max(0, hostMemPct ?? 0))}%`,
                    }}
                  />
                </div>
                <div className="flex justify-between text-[11px] text-slate-500 mt-1 font-mono">
                  <span>used: {stats.host.memory_used_bytes?.toLocaleString() ?? '—'} B</span>
                  <span>total: {stats.host.memory_total_bytes?.toLocaleString() ?? '—'} B</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Scheduler Capacity Ledger (Configured vs Reserved vs Available + Headroom) */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Database className="w-4 h-4 text-emerald-400" />
              FIFO Scheduler Capacity &amp; Headroom
            </h3>
            <span className="text-[11px] font-mono text-slate-400">
              Headroom: {stats.headroom.cpu_millis} mCPU / {stats.headroom.memory_mib} MiB
            </span>
          </div>

          <div className="space-y-3 text-xs">
            {/* Slots */}
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-slate-300">Reserved Session Slots</span>
                <span className="font-mono text-slate-200">
                  <strong className="text-emerald-400">{stats.reserved.slots}</strong> / {stats.budget.slots} slots
                  <span className="text-slate-400"> ({stats.available.slots} free)</span>
                </span>
              </div>
              <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 transition-all duration-300"
                  style={{
                    width: `${
                      stats.budget.slots > 0
                        ? Math.min(100, (stats.reserved.slots / stats.budget.slots) * 100)
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            {/* CPU Budget */}
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-slate-300">Reserved CPU Budget</span>
                <span className="font-mono text-slate-200">
                  <strong className="text-sky-400">{stats.reserved.cpu_millis} mCPU</strong> / {stats.budget.cpu_millis} mCPU
                  <span className="text-slate-400"> ({stats.available.cpu_millis} mCPU free)</span>
                </span>
              </div>
              <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-sky-500 transition-all duration-300"
                  style={{
                    width: `${
                      stats.budget.cpu_millis > 0
                        ? Math.min(100, (stats.reserved.cpu_millis / stats.budget.cpu_millis) * 100)
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            {/* Memory Budget */}
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-slate-300">Reserved Memory Budget</span>
                <span className="font-mono text-slate-200">
                  <strong className="text-amber-400">{stats.reserved.memory_mib} MiB</strong> / {stats.budget.memory_mib} MiB
                  <span className="text-slate-400"> ({stats.available.memory_mib} MiB free)</span>
                </span>
              </div>
              <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-500 transition-all duration-300"
                  style={{
                    width: `${
                      stats.budget.memory_mib > 0
                        ? Math.min(100, (stats.reserved.memory_mib / stats.budget.memory_mib) * 100)
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Modest Time-Series Charts (Concurrent Sessions & Resource Utilization) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Chart 1: Concurrent Running & Queued Sessions */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-400" />
              Concurrent Running &amp; Queued Sessions (Last {history.length} Samples)
            </h3>
            <div className="flex items-center gap-3 text-[11px]">
              <span className="flex items-center gap-1 text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400" /> Running
              </span>
              <span className="flex items-center gap-1 text-amber-400">
                <span className="w-2 h-2 rounded-full bg-amber-400" /> Queued
              </span>
              <span className="flex items-center gap-1 text-sky-400">
                <span className="w-2 h-2 rounded-full bg-sky-400" /> Provisioning
              </span>
            </div>
          </div>

          <div className="h-32 w-full bg-slate-950/60 border border-slate-800/80 rounded-lg p-2 flex items-end gap-1">
            {history.map((pt, i) => {
              const maxScale = Math.max(
                stats.budget.slots,
                ...history.map((h) => h.running + h.queued + h.provisioning),
                1,
              );
              const runH = (pt.running / maxScale) * 100;
              const provH = (pt.provisioning / maxScale) * 100;
              const queueH = (pt.queued / maxScale) * 100;
              return (
                <div
                  key={`${pt.sampledAt}-${i}`}
                  className="flex-1 h-full flex flex-col justify-end items-stretch gap-[1px]"
                  title={`${formatUtcTime(pt.sampledAt)} — Running: ${pt.running}, Provisioning: ${pt.provisioning}, Queued: ${pt.queued}`}
                >
                  {pt.queued > 0 && (
                    <div
                      className="bg-amber-400/80 rounded-t-[2px]"
                      style={{ height: `${Math.max(4, queueH)}%` }}
                    />
                  )}
                  {pt.provisioning > 0 && (
                    <div
                      className="bg-sky-400/80"
                      style={{ height: `${Math.max(4, provH)}%` }}
                    />
                  )}
                  {pt.running > 0 && (
                    <div
                      className="bg-emerald-500 rounded-b-[2px]"
                      style={{ height: `${Math.max(4, runH)}%` }}
                    />
                  )}
                  {pt.running === 0 && pt.queued === 0 && pt.provisioning === 0 && (
                    <div className="bg-slate-800 h-[2px] w-full" />
                  )}
                </div>
              );
            })}
          </div>
          <div className="flex justify-between text-[11px] text-slate-500 font-mono">
            <span>Cap: {stats.budget.slots} running slots</span>
            <span>
              Current: {stats.counts.RUNNING ?? 0} running, {stats.counts.QUEUED ?? 0} queued
            </span>
          </div>
        </div>

        {/* Chart 2: Resource Utilization (%) */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Layers className="w-4 h-4 text-sky-400" />
              Host &amp; Reserved Utilization % (Last {history.length} Samples)
            </h3>
            <div className="flex flex-wrap items-center gap-3 text-[11px]">
              <span className="flex items-center gap-1 text-sky-400">
                <span className="w-2 h-2 rounded-full bg-sky-400" /> Host CPU %
              </span>
              <span className="flex items-center gap-1 text-purple-400">
                <span className="w-2 h-2 rounded-full bg-purple-400" /> Host RAM %
              </span>
              <span className="flex items-center gap-1 text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400" /> Reserved CPU %
              </span>
            </div>
          </div>

          <div className="h-32 w-full bg-slate-950/60 border border-slate-800/80 rounded-lg p-2 flex items-end gap-1">
            {history.map((pt, i) => (
              <div
                key={`${pt.sampledAt}-${i}`}
                className="flex-1 h-full flex items-end gap-[1px]"
                title={`${formatUtcTime(pt.sampledAt)} — Host CPU: ${
                  pt.hostCpuPct == null ? 'UNAVAILABLE' : pt.hostCpuPct.toFixed(1) + '%'
                }, Host RAM: ${
                  pt.hostMemPct == null ? 'UNAVAILABLE' : pt.hostMemPct.toFixed(1) + '%'
                }, Reserved CPU: ${pt.reservedCpuPct.toFixed(0)}%`}
              >
                <div
                  className={`flex-1 rounded-t-[1px] ${
                    pt.hostCpuPct == null ? 'bg-slate-800/50' : 'bg-sky-400'
                  }`}
                  style={{
                    height: `${pt.hostCpuPct == null ? 3 : Math.max(4, Math.min(100, pt.hostCpuPct))}%`,
                  }}
                />
                <div
                  className={`flex-1 rounded-t-[1px] ${
                    pt.hostMemPct == null ? 'bg-slate-800/50' : 'bg-purple-400'
                  }`}
                  style={{
                    height: `${pt.hostMemPct == null ? 3 : Math.max(4, Math.min(100, pt.hostMemPct))}%`,
                  }}
                />
                <div
                  className="flex-1 bg-emerald-500/80 rounded-t-[1px]"
                  style={{ height: `${Math.max(2, Math.min(100, pt.reservedCpuPct))}%` }}
                />
              </div>
            ))}
          </div>
          <div className="flex justify-between text-[11px] text-slate-500 font-mono">
            <span>0% &ndash; 100% scale (null host CPU samples not plotted as 0%)</span>
            <span>
              Reserved: {((stats.reserved.cpu_millis / stats.budget.cpu_millis) * 100).toFixed(0)}% CPU /{' '}
              {((stats.reserved.memory_mib / stats.budget.memory_mib) * 100).toFixed(0)}% RAM
            </span>
          </div>
        </div>
      </div>

      {/* Live FIFO Queue Inspection */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <Clock className="w-4 h-4 text-amber-400" />
            FIFO Admission Queue ({queuedSessions.length} Waiting)
          </h3>
          {headBlockingReasons.length > 0 && (
            <span className="text-xs px-2.5 py-1 rounded bg-amber-500/15 border border-amber-500/30 text-amber-300">
              Head blocked: {headBlockingReasons.join(' · ')}
            </span>
          )}
        </div>

        {queuedSessions.length === 0 ? (
          <p className="text-xs text-slate-500 italic">
            Queue is currently empty. Eligible requests are admitted immediately in FIFO order.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {queuedSessions.map(({ id, position, session }) => (
              <div
                key={id}
                className="p-3 rounded-lg bg-slate-950/70 border border-amber-500/30 flex items-center justify-between text-xs"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono font-bold">
                      #{position}
                    </span>
                    <span className="font-mono text-slate-200 font-semibold">
                      {id.slice(0, 12)}
                    </span>
                  </div>
                  <div className="text-slate-400">
                    Owner: <span className="text-slate-200 font-medium">{session?.owner ?? '—'}</span> &middot;{' '}
                    <span className="font-mono">
                      {session?.cpu_millis ?? '?'} mCPU / {session?.memory_mib ?? '?'} MiB
                    </span>
                  </div>
                </div>
                <div className="text-right font-mono text-amber-300">
                  {session?.queue_seconds != null ? `${session.queue_seconds.toFixed(1)}s` : '—'}
                  <div className="text-[10px] text-slate-500">waiting</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sessions Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <Server className="w-4 h-4 text-sky-400" />
            All Sessions &amp; Container Telemetry ({sortedSessions.length})
          </h3>
          {stats.containers === null && (
            <span className="px-2.5 py-1 rounded text-xs font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
              DOCKER CONTAINER INVENTORY UNAVAILABLE (sampled {formatUtcTime(stats.sampled_at)})
            </span>
          )}
        </div>

        {sortedSessions.length === 0 ? (
          <p className="text-xs text-slate-500 italic">No sessions submitted yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-400">
                  <th className="py-2.5 px-3">Session ID</th>
                  <th className="py-2.5 px-3">Demo Owner</th>
                  <th className="py-2.5 px-3">Workload Type</th>
                  <th className="py-2.5 px-3">State</th>
                  <th className="py-2.5 px-3">Container ID</th>
                  <th className="py-2.5 px-3">Allocated Limits</th>
                  <th className="py-2.5 px-3">Measured Container Resource Usage</th>
                  <th className="py-2.5 px-3">Created (UTC)</th>
                  <th className="py-2.5 px-3">Queue / Provision Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {sortedSessions.map((s) => {
                  const sample: ContainerSample | undefined =
                    stats.containers != null ? stats.containers[s.id] : undefined;
                  const sampleStale =
                    sample != null && (snapshotStale || isSampleStale(sample.sampled_at, nowMs));
                  const cpuRatePct = containerCpuRates[s.id];

                  return (
                    <tr key={s.id} className="hover:bg-slate-800/30">
                      <td className="py-2.5 px-3 font-mono text-slate-200 select-all" title={s.id}>
                        {s.id.slice(0, 12)}
                      </td>
                      <td className="py-2.5 px-3 font-medium text-slate-200">{s.owner}</td>
                      <td className="py-2.5 px-3 text-slate-400 font-mono text-[11px]">
                        linux-shell (/bin/sleep + PTY)
                      </td>
                      <td className="py-2.5 px-3">
                        <div className="flex flex-col items-start gap-1">
                          {getStateBadge(s.state, s.queue_position)}
                          {s.cleanup_pending && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
                              cleanup_pending
                            </span>
                          )}
                          {s.failure && (
                            <span className="text-[10px] text-rose-400">{s.failure}</span>
                          )}
                        </div>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-300">
                        {s.container_id ? s.container_id.slice(0, 12) : '—'}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-300">
                        {s.cpu_millis} mCPU / {s.memory_mib} MiB
                      </td>
                      <td className="py-2.5 px-3">
                        {s.state !== 'RUNNING' ? (
                          <span className="text-slate-500 italic text-[11px]">
                            Not running ({s.state})
                          </span>
                        ) : stats.containers === null ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
                            UNAVAILABLE (@ {formatUtcTime(stats.sampled_at)})
                          </span>
                        ) : !sample || !sample.available ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
                            UNAVAILABLE (@ {formatUtcTime(sample?.sampled_at ?? stats.sampled_at)})
                          </span>
                        ) : (
                          <div className="space-y-0.5 font-mono text-[11px]">
                            <div className="flex items-center gap-2">
                              <span className="text-sky-300">
                                CPU:{' '}
                                {sample.cpu_usage_ns != null
                                  ? `${(sample.cpu_usage_ns / 1e9).toFixed(2)}s total`
                                  : 'UNAVAILABLE'}
                                {cpuRatePct != null ? ` (${cpuRatePct.toFixed(1)}%)` : ''}
                              </span>
                              <span className="text-slate-600">&middot;</span>
                              <span className="text-purple-300">
                                RAM: {formatBytesToMib(sample.memory_usage_bytes)}
                                {sample.memory_usage_bytes != null
                                  ? ` (${(
                                      (sample.memory_usage_bytes / (s.memory_mib * 1024 * 1024)) *
                                      100
                                    ).toFixed(1)}%)`
                                  : ''}
                              </span>
                            </div>
                            <div className="text-[10px] text-slate-500 flex items-center gap-1.5">
                              <span>sampled {formatUtcTime(sample.sampled_at)}</span>
                              {sampleStale && (
                                <span className="px-1 py-0.2 rounded bg-amber-500/20 text-amber-300 font-semibold">
                                  STALE
                                </span>
                              )}
                            </div>
                          </div>
                        )}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-400" title={s.created_at}>
                        {formatUtcTime(s.created_at)}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-300">
                        <div>
                          Wait:{' '}
                          {s.queue_seconds != null ? `${s.queue_seconds.toFixed(2)}s` : '—'}
                        </div>
                        <div className="text-slate-400">
                          Prov:{' '}
                          {s.provisioning_seconds != null
                            ? `${s.provisioning_seconds.toFixed(2)}s`
                            : '—'}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Allocation, Queue Advancement, Failure & Cleanup Event Log */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <Activity className="w-4 h-4 text-purple-400" />
            Lifecycle, Queue Advancement, Failure &amp; Cleanup Events ({allEvents.length})
          </h3>
          <span className="text-[11px] text-slate-500">
            Ordered newest first from authoritative session event log
          </span>
        </div>

        {allEvents.length === 0 ? (
          <p className="text-xs text-slate-500 italic">No lifecycle events recorded yet.</p>
        ) : (
          <div className="max-h-64 overflow-y-auto divide-y divide-slate-800/70 pr-1">
            {allEvents.slice(0, 60).map((ev) => {
              let detail = `${ev.cpuMillis} mCPU / ${ev.memoryMib} MiB`;
              if (ev.state === 'PROVISIONING' && ev.queueSeconds != null) {
                detail += ` — Admitted from FIFO queue after ${ev.queueSeconds.toFixed(2)}s wait`;
              } else if (ev.state === 'RUNNING' && ev.provisioningSeconds != null) {
                detail += ` — Container started in ${ev.provisioningSeconds.toFixed(2)}s`;
              } else if (ev.state === 'RELEASING') {
                detail += ev.cleanupPending
                  ? ' — Releasing container (cleanup_pending=true)'
                  : ' — Stopping & removing container';
              } else if (ev.state === 'RELEASED' || ev.state === 'COMPLETED' || ev.state === 'CANCELLED') {
                detail += ' — Cleanup confirmed & capacity returned to scheduler';
              } else if (ev.state === 'FAILED') {
                detail += ` — Failure: ${ev.failure ?? 'Unknown error'}`;
              }

              return (
                <div
                  key={ev.key}
                  className="py-2 flex flex-wrap items-center justify-between gap-2 text-xs"
                >
                  <div className="flex flex-wrap items-center gap-2.5">
                    {getStateBadge(ev.state)}
                    <span className="font-mono text-slate-200 font-semibold">
                      {ev.sessionId.slice(0, 10)}
                    </span>
                    <span className="text-slate-400">
                      owner=<strong className="text-slate-200">{ev.owner}</strong>
                    </span>
                    <span className="text-slate-400 font-mono text-[11px]">{detail}</span>
                  </div>
                  <span className="font-mono text-[11px] text-slate-500" title={ev.at}>
                    {formatUtcTime(ev.at)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
