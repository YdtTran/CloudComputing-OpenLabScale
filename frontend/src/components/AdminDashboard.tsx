import { useEffect, useState, useCallback, useRef } from 'react';
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  Clock,
  Cpu,
  Eye,
  Filter,
  Lock,
  Play,
  RefreshCw,
  Square,
  Terminal,
  Zap,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getStats, runDemoScenario, stopDemoScenario } from '../api';
import type {
  AdminStats,
  ContainerSample,
  RecommendationDecision,
  Session,
  SessionState,
} from '../types';

const MAX_HISTORY = 61;
const MAX_SLOT_HISTORY = 19;
const SLOT_INTERVAL_MS = 10_000;

export type AdminView = 'dashboard' | 'demo' | 'tables' | 'notifications' | 'probes';

export interface AdminAlert {
  id: string;
  level: 'info' | 'warning' | 'danger';
  title: string;
  detail: string;
  at: string;
}

interface HistoryPoint {
  seq: number;
  label: string;
  sampledAt: string;
  running: number;
  queued: number;
  provisioning: number;
  hostCpuPct: number | null;
  hostMemPct: number | null;
  avgContainerCpuPct: number | null;
  ebpfIoKib: number;
  ebpfSockKib: number;
  ebpfOps: number;
  activeVerdicts: number;
  idleVerdicts: number;
  unknownVerdicts: number;
}

interface SlotPoint {
  seq: number;
  label: string;
  sampledAt: string;
  running: number;
  queued: number;
  slots: number;
}

type ChartRow = {
  seq: number;
  slot: number;
  sampledAt: string;
  [key: string]: string | number | null | undefined;
};

interface PrevContainerCpu {
  cpuNs: number;
  sampledAtMs: number;
}

interface AdminDashboardProps {
  token: string;
  identityLabel: string;
  activeView: AdminView;
  onNavigate: (view: AdminView) => void;
  onStatsSync?: (stats: AdminStats | null, alerts: AdminAlert[]) => void;
  externalSearch?: string;
  signingOut?: boolean;
}

function formatBytesToMib(bytes?: number | null): string {
  if (bytes == null || Number.isNaN(bytes)) return 'UNAVAILABLE';
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function formatBytesToGib(bytes?: number | null): string {
  if (bytes == null || Number.isNaN(bytes)) return '—';
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatUptime(seconds?: number | null): string {
  if (seconds == null || Number.isNaN(seconds) || seconds < 0) return '—';
  const total = Math.floor(seconds);
  const days = Math.floor(total / 86400);
  const hrs = Math.floor((total % 86400) / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${days}:${pad(hrs)}:${pad(mins)}:${pad(secs)}`;
}

function formatBytesCompact(bytes?: number | null): string {
  if (bytes == null || Number.isNaN(bytes)) return '—';
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${bytes} B`;
}

function formatShortTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(11, 19);
}

function formatUtcTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace('T', ' ').slice(11, 23) + ' UTC';
}

function createEmptyHistory(): HistoryPoint[] {
  return Array.from({ length: MAX_HISTORY }, (_, idx) => ({
    seq: idx,
    label: '',
    sampledAt: '',
    running: 0,
    queued: 0,
    provisioning: 0,
    hostCpuPct: 0,
    hostMemPct: 0,
    avgContainerCpuPct: 0,
    ebpfIoKib: 0,
    ebpfSockKib: 0,
    ebpfOps: 0,
    activeVerdicts: 0,
    idleVerdicts: 0,
    unknownVerdicts: 0,
  }));
}

function createEmptySlotHistory(): SlotPoint[] {
  return Array.from({ length: MAX_SLOT_HISTORY }, (_, idx) => ({
    seq: idx,
    label: '',
    sampledAt: '',
    running: 0,
    queued: 0,
    slots: 0,
  }));
}

function buildAlerts(data: AdminStats): AdminAlert[] {
  const alerts: AdminAlert[] = [];
  if (data.observability && data.observability.ebpf.status !== 'OK') {
    alerts.push({
      id: 'ebpf-health',
      level: 'warning',
      title: `eBPF Collector ${data.observability.ebpf.status}`,
      detail: data.observability.ebpf.reason,
      at: data.sampled_at,
    });
  }
  if (data.queue.length > 0) {
    alerts.push({
      id: 'fifo-backlog',
      level: data.queue.length >= 4 ? 'warning' : 'info',
      title: `FIFO Queue Waiting (${data.queue.length} request${data.queue.length > 1 ? 's' : ''})`,
      detail: `Cap ${data.reserved.slots}/${data.budget.slots} slots running`,
      at: data.sampled_at,
    });
  }
  for (const s of data.sessions) {
    const sample = data.containers?.[s.id];
    const owner = data.owner_names[s.owner] ?? s.owner;
    if (s.state === 'RUNNING' && sample?.recommendation?.decision === 'IDLE_CANDIDATE') {
      alerts.push({
        id: `idle-${s.id}`,
        level: 'warning',
        title: `Idle Candidate: ${owner} (${s.id.slice(0, 8)})`,
        detail: sample.recommendation.reason,
        at: sample.sampled_at,
      });
    } else if (s.state === 'FAILED') {
      alerts.push({
        id: `fail-${s.id}`,
        level: 'danger',
        title: `Session Failed: ${owner} (${s.id.slice(0, 8)})`,
        detail: s.failure ?? 'Container provisioning or runtime error',
        at: s.created_at,
      });
    }
  }
  return alerts;
}

export function AdminDashboard({
  token,
  identityLabel,
  activeView,
  onNavigate,
  onStatsSync,
  externalSearch = '',
  signingOut = false,
}: AdminDashboardProps) {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [authDenied, setAuthDenied] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>(createEmptyHistory);
  const [slotHistory, setSlotHistory] = useState<SlotPoint[]>(createEmptySlotHistory);
  const [containerCpuRates, setContainerCpuRates] = useState<Record<string, number | null>>({});
  const [perfTab, setPerfTab] = useState<'cpu' | 'memory' | 'slots' | 'ebpf' | 'verdicts'>('cpu');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [decisionFilter, setDecisionFilter] = useState<'ALL' | RecommendationDecision>('ALL');
  const [taskFilter, setTaskFilter] = useState<'ALL' | RecommendationDecision>('ALL');
  const [acknowledgedTasks, setAcknowledgedTasks] = useState<Record<string, boolean>>({});
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [demoBusy, setDemoBusy] = useState<string | null>(null);
  const [demoNotice, setDemoNotice] = useState<string | null>(null);
  const prevContainerCpuRef = useRef<Record<string, PrevContainerCpu>>({});
  const lastSlotSyncRef = useRef<number>(0);
  const seqRef = useRef<number>(MAX_HISTORY - 1);
  const slotSeqRef = useRef<number>(MAX_SLOT_HISTORY - 1);
  const signingOutRef = useRef<boolean>(signingOut);
  const onStatsSyncRef = useRef(onStatsSync);

  useEffect(() => {
    signingOutRef.current = signingOut;
  }, [signingOut]);

  useEffect(() => {
    onStatsSyncRef.current = onStatsSync;
  }, [onStatsSync]);

  useEffect(() => {
    if (externalSearch) {
      setSearchQuery(externalSearch);
    }
  }, [externalSearch]);

  const fetchSnapshot = useCallback(async (signal?: AbortSignal) => {
    if (signingOutRef.current || signal?.aborted) return;
    if (!token) {
      setAuthDenied('HTTP 401: Sign in required');
      return;
    }
    try {
      const data = await getStats(token, signal);
      if (signingOutRef.current || signal?.aborted) return;
      const sampleNowMs = Date.now();
      setAuthDenied(null);
      setPollError(null);
      setStats(data);
      onStatsSyncRef.current?.(data, buildAlerts(data));

      const cpuValues: number[] = [];
      let totalIoBytes = 0;
      let totalSockBytes = 0;
      let totalOps = 0;
      let activeVerdicts = 0;
      let idleVerdicts = 0;
      let unknownVerdicts = 0;

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

          const sigCpu = sample.signals?.cpu_pct ?? nextRates[sid];
          if (sigCpu != null) cpuValues.push(sigCpu);
          totalIoBytes += (sample.signals?.io_read_bytes_per_sec ?? 0) + (sample.signals?.io_write_bytes_per_sec ?? 0);
          totalSockBytes += (sample.signals?.sock_rx_bytes_per_sec ?? 0) + (sample.signals?.sock_tx_bytes_per_sec ?? 0);
          totalOps += (sample.signals?.io_events_delta ?? 0) + (sample.signals?.socket_events_delta ?? 0) + (sample.signals?.exec_events_delta ?? 0);

          const dec = sample.recommendation?.decision ?? 'UNKNOWN';
          if (dec === 'ACTIVE') activeVerdicts += 1;
          else if (dec === 'IDLE_CANDIDATE') idleVerdicts += 1;
          else unknownVerdicts += 1;
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

      const avgContainerCpuPct =
        cpuValues.length > 0 ? Number((cpuValues.reduce((a, b) => a + b, 0) / cpuValues.length).toFixed(1)) : null;

      seqRef.current += 1;
      const point: HistoryPoint = {
        seq: seqRef.current,
        label: formatShortTime(data.sampled_at),
        sampledAt: data.sampled_at,
        running: data.counts.RUNNING ?? 0,
        queued: data.counts.QUEUED ?? 0,
        provisioning: data.counts.PROVISIONING ?? 0,
        hostCpuPct: data.host.available && data.host.cpu_utilization_pct != null ? Number(data.host.cpu_utilization_pct.toFixed(1)) : null,
        hostMemPct: hostMemPct != null ? Number(hostMemPct.toFixed(1)) : null,
        avgContainerCpuPct,
        ebpfIoKib: Number((totalIoBytes / 1024).toFixed(1)),
        ebpfSockKib: Number((totalSockBytes / 1024).toFixed(1)),
        ebpfOps: totalOps,
        activeVerdicts,
        idleVerdicts,
        unknownVerdicts,
      };
      setHistory((prev) => [...prev.slice(-(MAX_HISTORY - 1)), point]);
      if (lastSlotSyncRef.current === 0 || sampleNowMs - lastSlotSyncRef.current >= SLOT_INTERVAL_MS) {
        lastSlotSyncRef.current = sampleNowMs;
        slotSeqRef.current += 1;
        setSlotHistory((prev) => [
          ...prev.slice(-(MAX_SLOT_HISTORY - 1)),
          {
            seq: slotSeqRef.current,
            label: point.label,
            sampledAt: point.sampledAt,
            running: point.running,
            queued: point.queued,
            slots: data.budget.slots,
          },
        ]);
      }
    } catch (err: unknown) {
      if ((err instanceof DOMException && err.name === 'AbortError') || signal?.aborted || signingOutRef.current) {
        return;
      }
      const msg = err instanceof Error ? err.message : 'Failed to fetch /stats';
      if (msg.includes('401') || msg.includes('403')) {
        setAuthDenied(msg);
      } else {
        setPollError(msg);
      }
    }
  }, [token]);

  useEffect(() => {
    if (signingOut) return;
    const ctrl = new AbortController();
    void fetchSnapshot(ctrl.signal);
    return () => ctrl.abort();
  }, [fetchSnapshot, signingOut]);

  useEffect(() => {
    if (authDenied || signingOut) return;
    let ctrl: AbortController | null = null;
    const timer = setInterval(() => {
      ctrl?.abort();
      ctrl = new AbortController();
      void fetchSnapshot(ctrl.signal);
    }, 1000);
    return () => {
      clearInterval(timer);
      ctrl?.abort();
    };
  }, [authDenied, signingOut, fetchSnapshot]);

  async function launchDemo(scenarioId: string) {
    setDemoBusy(scenarioId);
    setDemoNotice(null);
    try {
      await runDemoScenario(token, scenarioId);
      await fetchSnapshot();
    } catch (err: unknown) {
      setDemoNotice(err instanceof Error ? err.message : 'Failed to start demo');
    } finally {
      setDemoBusy(null);
    }
  }

  async function haltDemo() {
    setDemoBusy('stop');
    setDemoNotice(null);
    try {
      await stopDemoScenario(token);
      await fetchSnapshot();
    } catch (err: unknown) {
      setDemoNotice(err instanceof Error ? err.message : 'Failed to stop demo');
    } finally {
      setDemoBusy(null);
    }
  }

  if (authDenied) {
    return (
      <div className="bg-[#27293d] border border-[#fd5d93]/40 rounded-lg p-8 flex flex-col items-center justify-center text-center my-4 shadow-lg">
        <div className="p-4 bg-[#fd5d93]/10 border border-[#fd5d93]/30 rounded-full text-[#fd5d93] mb-4">
          <Lock className="w-8 h-8" />
        </div>
        <h2 className="text-base font-semibold text-white mb-2">Administrator Access Denied</h2>
        <p className="text-xs text-[#fd5d93] font-mono mb-3 px-3 py-1.5 rounded bg-[#1e1e2f] border border-[#fd5d93]/30">
          GET /stats &rarr; {authDenied}
        </p>
        <p className="text-xs text-[#9a9a9a] max-w-lg">{identityLabel} cannot access this dashboard.</p>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="bg-[#27293d] rounded-lg p-8 flex items-center justify-center gap-3 text-xs text-[#9a9a9a] shadow-lg">
        <RefreshCw className="w-4 h-4 animate-spin text-[#1d8cf8]" />
        Loading live telemetry snapshot from GET /stats...
      </div>
    );
  }

  const sortedSessions = [...stats.sessions].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  const runningSessions = sortedSessions.filter((s) => s.state === 'RUNNING');
  const activeAlerts = buildAlerts(stats);

  const normalizedQuery = searchQuery.trim().toLowerCase();
  const filteredSessions = sortedSessions.filter((s) => {
    const ownerName = (stats.owner_names[s.owner] ?? s.owner).toLowerCase();
    const matchesText =
      !normalizedQuery ||
      s.id.toLowerCase().includes(normalizedQuery) ||
      ownerName.includes(normalizedQuery) ||
      (s.container_id ?? '').toLowerCase().includes(normalizedQuery);
    if (!matchesText) return false;
    if (decisionFilter === 'ALL') return true;
    return (stats.containers?.[s.id]?.recommendation?.decision ?? 'UNKNOWN') === decisionFilter;
  });

  const taskSessions = runningSessions.filter((s) => {
    if (taskFilter === 'ALL') return true;
    return (stats.containers?.[s.id]?.recommendation?.decision ?? 'UNKNOWN') === taskFilter;
  });

  const selectedSession =
    (selectedSessionId ? sortedSessions.find((s) => s.id === selectedSessionId) : undefined) ??
    runningSessions[0];
  const selectedSample = selectedSession && stats.containers ? stats.containers[selectedSession.id] : undefined;

  const sessionMap = new Map<string, Session>(stats.sessions.map((s) => [s.id, s]));
  const queuedSessions = stats.queue.map((id, idx) => ({ id, position: idx + 1, session: sessionMap.get(id) }));

  const totalEbpfIoBytes = Object.values(stats.containers ?? {}).reduce(
    (sum, c) => sum + (c.signals?.io_read_bytes_total ?? 0) + (c.signals?.io_write_bytes_total ?? 0),
    0,
  );
  const totalEbpfSockBytes = Object.values(stats.containers ?? {}).reduce(
    (sum, c) => sum + (c.signals?.sock_rx_bytes_total ?? 0) + (c.signals?.sock_tx_bytes_total ?? 0),
    0,
  );
  const totalEbpfOps = Object.values(stats.containers ?? {}).reduce(
    (sum, c) => sum + (c.signals?.io_events_delta ?? 0) + (c.signals?.socket_events_delta ?? 0) + (c.signals?.exec_events_delta ?? 0),
    0,
  );

  const ebpfBarData =
    runningSessions.length > 0
      ? runningSessions.map((s, idx) => {
          const sig = stats.containers?.[s.id]?.signals;
          const owner = stats.owner_names[s.owner] ?? `s${idx + 1}`;
          const bytes = (sig?.io_read_bytes_per_sec ?? 0) + (sig?.io_write_bytes_per_sec ?? 0) + (sig?.sock_rx_bytes_per_sec ?? 0) + (sig?.sock_tx_bytes_per_sec ?? 0);
          return {
            name: owner.slice(0, 8),
            kibPerSec: Number((bytes / 1024).toFixed(1)),
            ops: (sig?.io_events_delta ?? 0) + (sig?.socket_events_delta ?? 0) + (sig?.exec_events_delta ?? 0),
          };
        })
      : history.slice(-6).map((h) => ({ name: h.label.slice(3), kibPerSec: Number((h.ebpfIoKib + h.ebpfSockKib).toFixed(1)), ops: h.ebpfOps }));

  const verdictCounts = runningSessions.reduce(
    (acc, s) => {
      const d = stats.containers?.[s.id]?.recommendation?.decision ?? 'UNKNOWN';
      if (d === 'ACTIVE') acc.active += 1;
      else if (d === 'IDLE_CANDIDATE') acc.idle += 1;
      else acc.unknown += 1;
      return acc;
    },
    { active: 0, idle: 0, unknown: 0 },
  );

  const latestPoint = history[history.length - 1];
  const hostCpuVal =
    stats.host.available && stats.host.cpu_utilization_pct != null
      ? Number(stats.host.cpu_utilization_pct.toFixed(1))
      : null;
  const hostMemUsed = stats.host.available ? (stats.host.memory_used_bytes ?? null) : null;
  const hostMemTotal = stats.host.available ? (stats.host.memory_total_bytes ?? null) : null;
  const hostMemFree =
    hostMemUsed != null && hostMemTotal != null ? Math.max(0, hostMemTotal - hostMemUsed) : null;
  const hostMemPctVal =
    hostMemUsed != null && hostMemTotal != null && hostMemTotal > 0
      ? Number(((hostMemUsed / hostMemTotal) * 100).toFixed(1))
      : null;
  const hostSpeedGhz =
    stats.host.cpu_mhz != null && stats.host.cpu_mhz > 0
      ? `${(stats.host.cpu_mhz / 1000).toFixed(2)} GHz`
      : '—';
  const latestSlot = slotHistory[slotHistory.length - 1] ?? {
    label: formatShortTime(stats.sampled_at),
    sampledAt: stats.sampled_at,
    running: stats.counts.RUNNING ?? 0,
    queued: stats.counts.QUEUED ?? 0,
    slots: stats.budget.slots,
  };
  const chartHistory: ChartRow[] = history.map((pt, idx) => ({ ...pt, slot: idx }));
  const sparkHistory: ChartRow[] = history.slice(-24).map((pt, idx) => ({ ...pt, slot: idx }));
  const slotChartHistory: ChartRow[] = slotHistory.map((pt, idx) => ({ ...pt, slot: idx }));
  const perfSubtitleMap = {
    cpu:
      stats.host.cpu_model ??
      `Linux cgroup v2 (${stats.host.logical_cpus ?? (stats.budget.cpu_millis / 1000).toFixed(0)} logical CPUs)`,
    memory: hostMemTotal != null ? `${formatBytesToGib(hostMemTotal)} Host RAM · cgroup v2` : 'Host Memory & Cgroup Budget',
    slots: '',
    ebpf: `libbpf CO-RE (${stats.observability?.ebpf.probes.length ?? 0} probes attached)`,
    verdicts: `${verdictCounts.active} ACTIVE · ${verdictCounts.idle} IDLE · ${verdictCounts.unknown} UNKNOWN`,
  } as const;

  const getStateBadge = (state: SessionState, queuePos?: number | null) => {
    switch (state) {
      case 'RUNNING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[#00f2c3]/15 text-[#00f2c3] border border-[#00f2c3]/30">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00f2c3] animate-pulse" />
            RUNNING
          </span>
        );
      case 'PROVISIONING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[#1d8cf8]/15 text-[#1d8cf8] border border-[#1d8cf8]/30">
            <RefreshCw className="w-3 h-3 animate-spin" />
            PROVISIONING
          </span>
        );
      case 'REQUESTED':
      case 'QUEUED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[#ff8d72]/15 text-[#ff8d72] border border-[#ff8d72]/30">
            <Clock className="w-3 h-3" />
            {state} {queuePos ? `#${queuePos}` : ''}
          </span>
        );
      case 'RELEASING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[#e14eca]/15 text-[#e14eca] border border-[#e14eca]/30">
            RELEASING
          </span>
        );
      case 'RELEASED':
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-[#1e1e2f] text-[#9a9a9a] border border-white/10">
            <CheckCircle2 className="w-3 h-3 text-[#00f2c3]" />
            {state}
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[#fd5d93]/15 text-[#fd5d93] border border-[#fd5d93]/30">
            {state}
          </span>
        );
    }
  };

  const getRecommendationBadge = (decision?: RecommendationDecision) => {
    switch (decision) {
      case 'ACTIVE':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#00f2c3]/15 text-[#00f2c3] border border-[#00f2c3]/40">
            ACTIVE
          </span>
        );
      case 'IDLE_CANDIDATE':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#e14eca]/15 text-[#e14eca] border border-[#e14eca]/40">
            IDLE_CANDIDATE
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#1e1e2f] text-[#9a9a9a] border border-white/10">
            UNKNOWN
          </span>
        );
    }
  };

  const sessionDetailPanel = selectedSession && selectedSample && (
    <div className="bg-[#27293d] rounded-lg p-5 shadow-lg border border-white/5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <Terminal className="w-4 h-4 text-[#1d8cf8]" />
          <span className="text-xs uppercase tracking-wider text-[#9a9a9a]">Selected Session Telemetry</span>
          <span className="font-mono text-sm text-white font-semibold">{selectedSession.id.slice(0, 12)}</span>
          <span className="text-xs text-[#9a9a9a]">({stats.owner_names[selectedSession.owner] ?? selectedSession.owner})</span>
          {getRecommendationBadge(selectedSample.recommendation?.decision)}
        </div>
        <span className="text-[11px] font-mono text-[#9a9a9a]">
          cgroup_id={selectedSample.signals?.cgroup_id ?? '—'} &middot; quality={selectedSample.signal_quality?.status ?? 'UNAVAILABLE'} &middot; read-only
        </span>
      </div>

      {selectedSample.recommendation && (
        <p className="text-xs text-slate-200 bg-[#1e1e2f] px-3 py-2 rounded border border-white/5">
          <strong className="text-[#00f2c3]">Verdict Reason:</strong> {selectedSample.recommendation.reason}
        </p>
      )}

      {selectedSample.signals && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
          <div className="p-3 rounded bg-[#1e1e2f] border border-white/5">
            <div className="text-[#9a9a9a] text-[10px] uppercase">CPU / PSI avg10</div>
            <div className="text-[#1d8cf8] font-semibold mt-1">
              {selectedSample.signals.cpu_pct ?? '—'}% / PSI {selectedSample.signals.psi_cpu_some_avg10 ?? '—'}
            </div>
          </div>
          <div className="p-3 rounded bg-[#1e1e2f] border border-white/5">
            <div className="text-[#9a9a9a] text-[10px] uppercase">VFS Tmpfs I/O (R/W total)</div>
            <div className="text-[#00f2c3] font-semibold mt-1">
              {formatBytesCompact(selectedSample.signals.io_read_bytes_total)} / {formatBytesCompact(selectedSample.signals.io_write_bytes_total)}
            </div>
          </div>
          <div className="p-3 rounded bg-[#1e1e2f] border border-white/5">
            <div className="text-[#9a9a9a] text-[10px] uppercase">Socket (RX/TX total)</div>
            <div className="text-[#e14eca] font-semibold mt-1">
              {formatBytesCompact(selectedSample.signals.sock_rx_bytes_total)} / {formatBytesCompact(selectedSample.signals.sock_tx_bytes_total)}
            </div>
          </div>
          <div className="p-3 rounded bg-[#1e1e2f] border border-white/5">
            <div className="text-[#9a9a9a] text-[10px] uppercase">Last Interaction / Exec</div>
            <div className="text-white font-semibold mt-1">
              {selectedSample.signals.interaction_age_seconds != null ? `${selectedSample.signals.interaction_age_seconds}s ago` : 'None'}
              {selectedSample.signals.recent_comm ? ` · ${selectedSample.signals.recent_comm}` : ''}
            </div>
          </div>
        </div>
      )}
    </div>
  );

  if (activeView === 'demo') {
    const scenarios = stats.demo?.scenarios ?? [];
    return (
      <div className="space-y-6">
        <div className="bg-[#27293d] rounded-lg p-6 shadow-lg border border-white/5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-wider text-[#9a9a9a]">Live Workload Orchestrator</p>
              <h2 className="text-2xl font-light text-white mt-0.5">Challenging Demo Scenarios</h2>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onNavigate('dashboard')}
                className="px-3 py-1.5 rounded bg-[#1e1e2f] border border-[#1d8cf8]/50 text-[#1d8cf8] text-xs font-semibold hover:bg-[#1d8cf8]/10 transition cursor-pointer"
              >
                Watch Live on Dashboard &rarr;
              </button>
              <button
                type="button"
                disabled={demoBusy !== null}
                onClick={() => void haltDemo()}
                className="px-3 py-1.5 rounded bg-[#fd5d93]/20 border border-[#fd5d93]/50 text-[#fd5d93] text-xs font-semibold hover:bg-[#fd5d93]/30 transition flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                <Square className="w-3.5 h-3.5" />
                Stop &amp; Release Demo
              </button>
            </div>
          </div>

          <div className="p-3 rounded bg-[#1e1e2f] border border-white/5 text-xs flex flex-wrap items-center justify-between gap-2">
            <span className="text-slate-200">
              Status: <strong className="text-[#00f2c3] uppercase">{stats.demo?.state ?? 'idle'}</strong> &middot;{' '}
              {demoNotice ? <span className="text-[#fd5d93]">{demoNotice}</span> : (stats.demo?.message ?? 'Ready')}
            </span>
            <span className="font-mono text-[#9a9a9a]">
              Submitted: {stats.demo?.total_submitted ?? 0} &middot; Active demo sessions: {stats.demo?.active_demo_sessions ?? 0} &middot; Completed: {stats.demo?.completed_count ?? 0}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {scenarios.map((sc) => (
              <div
                key={sc.id}
                className="bg-[#1e1e2f] rounded-lg p-5 border border-white/5 hover:border-[#1d8cf8]/50 transition flex flex-col justify-between gap-4"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#1d8cf8]/15 text-[#1d8cf8]">
                      {sc.requests} requests &middot; ~{sc.duration_seconds}s
                    </span>
                    <Zap className="w-4 h-4 text-[#e14eca]" />
                  </div>
                  <h3 className="text-sm font-semibold text-white">{sc.title}</h3>
                  <p className="text-xs text-[#9a9a9a] leading-relaxed">{sc.description}</p>
                </div>
                <button
                  type="button"
                  disabled={demoBusy !== null || stats.demo?.state === 'running'}
                  onClick={() => void launchDemo(sc.id)}
                  className="w-full py-2 px-3 rounded bg-gradient-to-r from-[#1d8cf8] to-[#3358f4] text-white text-xs font-semibold hover:opacity-90 transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {demoBusy === sc.id ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                  Launch Scenario
                </button>
              </div>
            ))}
          </div>
        </div>
        {sessionDetailPanel}
      </div>
    );
  }

  if (activeView === 'notifications') {
    return (
      <div className="space-y-6">
        <div className="bg-[#27293d] rounded-lg p-6 shadow-lg border border-white/5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-wider text-[#9a9a9a]">Real-Time Alert Center</p>
              <h2 className="text-2xl font-light text-white mt-0.5">Notifications ({activeAlerts.length})</h2>
            </div>
            <Bell className="w-5 h-5 text-[#e14eca]" />
          </div>
          {activeAlerts.length === 0 ? (
            <p className="text-xs text-[#9a9a9a] py-6 text-center">No active alerts. Scheduler and eBPF signals are healthy.</p>
          ) : (
            <div className="space-y-3">
              {activeAlerts.map((a) => (
                <div
                  key={a.id}
                  className={`p-4 rounded-lg border flex items-start justify-between gap-3 text-xs ${
                    a.level === 'danger'
                      ? 'bg-[#fd5d93]/10 border-[#fd5d93]/40 text-[#fd5d93]'
                      : a.level === 'warning'
                        ? 'bg-[#ff8d72]/10 border-[#ff8d72]/40 text-[#ff8d72]'
                        : 'bg-[#1d8cf8]/10 border-[#1d8cf8]/40 text-[#1d8cf8]'
                  }`}
                >
                  <div>
                    <div className="font-semibold text-white">{a.title}</div>
                    <div className="text-[#9a9a9a] mt-1">{a.detail}</div>
                  </div>
                  <span className="font-mono text-[11px] shrink-0">{formatUtcTime(a.at)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (activeView === 'probes') {
    const probes = stats.observability?.ebpf.probes ?? [];
    return (
      <div className="space-y-6">
        <div className="bg-[#27293d] rounded-lg p-6 shadow-lg border border-white/5 space-y-4">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-[#9a9a9a]">Kernel CO-RE Instrumentation</p>
            <h2 className="text-2xl font-light text-white mt-0.5">Attached eBPF Probes &amp; Cgroup Signals</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {probes.map((probe) => (
              <div key={probe} className="p-4 rounded-lg bg-[#1e1e2f] border border-white/5 hover:border-[#00f2c3]/40 transition">
                <div className="flex items-center justify-between mb-2">
                  <Cpu className="w-4 h-4 text-[#00f2c3]" />
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#00f2c3]/15 text-[#00f2c3]">ATTACHED</span>
                </div>
                <div className="font-mono text-xs text-white font-semibold">{probe}</div>
              </div>
            ))}
            {probes.length === 0 && (
              <div className="col-span-full p-4 rounded bg-[#1e1e2f] text-xs text-[#fd5d93]">
                No eBPF probes currently attached ({stats.observability?.ebpf.reason ?? 'Unavailable'}).
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (activeView === 'tables') {
    return (
      <div className="space-y-6">
        {queuedSessions.length > 0 && (
          <div className="bg-[#27293d] rounded-lg p-5 shadow-lg border border-white/5 space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[#ff8d72] flex items-center gap-2">
              <Clock className="w-4 h-4" />
              FIFO Admission Queue ({queuedSessions.length} Waiting)
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {queuedSessions.map(({ id, position, session }) => (
                <div key={id} className="p-3 rounded bg-[#1e1e2f] border border-[#ff8d72]/30 text-xs flex justify-between items-center">
                  <div>
                    <div className="font-mono text-white font-semibold">
                      #{position} &middot; {id.slice(0, 10)}
                    </div>
                    <div className="text-[#9a9a9a] mt-0.5">
                      {session ? stats.owner_names[session.owner] ?? session.owner : '—'} &middot;{' '}
                      {stats.queue_reasons[id]?.join(', ') || 'Waiting'}
                    </div>
                  </div>
                  <span className="font-mono text-[#ff8d72]">{session?.queue_seconds?.toFixed(1) ?? '0.0'}s</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="bg-[#27293d] rounded-lg p-5 shadow-lg border border-white/5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-white">
              All Sessions &amp; Live eBPF Telemetry ({filteredSessions.length} / {sortedSessions.length})
            </h3>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search session, user, container..."
                className="px-3 py-1.5 rounded bg-[#1e1e2f] border border-white/10 text-white placeholder-[#9a9a9a] focus:outline-none focus:border-[#1d8cf8]"
              />
              {(['ALL', 'ACTIVE', 'IDLE_CANDIDATE', 'UNKNOWN'] as const).map((choice) => (
                <button
                  key={choice}
                  type="button"
                  onClick={() => setDecisionFilter(choice)}
                  className={`px-2.5 py-1 rounded text-[11px] font-semibold border cursor-pointer transition ${
                    decisionFilter === choice
                      ? 'bg-[#1d8cf8] border-[#1d8cf8] text-white'
                      : 'bg-[#1e1e2f] border-white/10 text-[#9a9a9a] hover:text-white'
                  }`}
                >
                  {choice}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-gray-700/50 text-[11px] uppercase tracking-wider text-[#9a9a9a]">
                  <th className="py-3 px-3">Session</th>
                  <th className="py-3 px-3">Owner</th>
                  <th className="py-3 px-3">State</th>
                  <th className="py-3 px-3">CPU / RAM</th>
                  <th className="py-3 px-3">eBPF VFS I/O · Sock · Exec</th>
                  <th className="py-3 px-3">Recommendation</th>
                  <th className="py-3 px-3 text-right">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/50">
                {filteredSessions.map((s) => {
                  const sample = stats.containers?.[s.id];
                  const cpuPct = sample?.signals?.cpu_pct ?? containerCpuRates[s.id];
                  const demoRole = stats.demo?.session_roles?.[s.id];
                  return (
                    <tr
                      key={s.id}
                      onClick={() => setSelectedSessionId(s.id)}
                      className={`cursor-pointer transition ${selectedSession?.id === s.id ? 'bg-[#1d8cf8]/10' : 'hover:bg-white/5'}`}
                    >
                      <td className="py-3 px-3 font-mono text-white">
                        {s.id.slice(0, 10)}
                        {demoRole && <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-[#e14eca]/20 text-[#e14eca]">{demoRole}</span>}
                      </td>
                      <td className="py-3 px-3 text-slate-200">{stats.owner_names[s.owner] ?? s.owner}</td>
                      <td className="py-3 px-3">{getStateBadge(s.state, s.queue_position)}</td>
                      <td className="py-3 px-3 font-mono text-slate-300">
                        {s.state === 'RUNNING' ? `${cpuPct != null ? cpuPct.toFixed(1) + '%' : '—'} · ${formatBytesToMib(sample?.memory_usage_bytes)}` : `${s.cpu_millis}m / ${s.memory_mib}M`}
                      </td>
                      <td className="py-3 px-3 font-mono text-[#9a9a9a]">
                        {sample?.signals
                          ? `IO ${sample.signals.io_events_delta ?? 0} (${formatBytesCompact(sample.signals.io_write_bytes_total)}) · Sock ${sample.signals.socket_events_delta ?? 0} · Exec ${sample.signals.exec_events_delta ?? 0}`
                          : '—'}
                      </td>
                      <td className="py-3 px-3">{s.state === 'RUNNING' ? getRecommendationBadge(sample?.recommendation?.decision) : '—'}</td>
                      <td className="py-3 px-3 text-right font-mono text-[#9a9a9a]">{formatShortTime(s.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        {sessionDetailPanel}
      </div>
    );
  }

  // Default Black Dashboard 3-row Layout ('dashboard')
  return (
    <div className="space-y-6">
      {pollError && (
        <div className="p-3 bg-[#ff8d72]/10 border border-[#ff8d72]/30 rounded-lg text-[#ff8d72] text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>Poll error: {pollError}. Showing last retained snapshot.</span>
        </div>
      )}

      {/* Row 1: Full-Width "Performance" Card (Windows 11 Task Manager Layout) */}
      <div className="bg-[#27293d] rounded-lg p-6 shadow-lg border border-white/5 hover:border-white/10 transition">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <h2 className="text-2xl font-light text-white">Performance</h2>

          <div className="flex items-center gap-2 text-xs text-[#9cb8d9] bg-[#1e1e2f] px-3 py-1.5 rounded-md border border-[#3b6ea5]/40">
            <Cpu className="w-3.5 h-3.5 text-[#4a85c5]" />
            <span className="font-mono">{stats.host.kernel_release ?? 'Linux host'}</span>
            <span className="text-white/25">|</span>
            <span>eBPF: {stats.observability?.ebpf.status ?? 'UNAVAILABLE'}</span>
          </div>
        </div>

        <div className="grid grid-cols-1 min-[560px]:grid-cols-[204px_1fr] md:grid-cols-[228px_1fr] lg:grid-cols-[260px_1fr] gap-5">
          {/* Left Panel: Task Manager Resource & Telemetry Selector */}
          <div className="flex flex-col gap-1.5 min-[560px]:border-r min-[560px]:border-white/10 min-[560px]:pr-4">
            {(
              [
                {
                  key: 'cpu' as const,
                  title: 'CPU',
                  line1: `${hostCpuVal != null ? `${hostCpuVal}%` : '—'} · ${hostSpeedGhz}`,
                  data: sparkHistory,
                  dataKey: 'hostCpuPct' as const,
                  stroke: '#4a85c5',
                  isPct: true,
                },
                {
                  key: 'memory' as const,
                  title: 'Memory',
                  line1:
                    hostMemUsed != null && hostMemTotal != null
                      ? `${formatBytesToGib(hostMemUsed).replace(' GB', '')}/${formatBytesToGib(hostMemTotal)} (${hostMemPctVal ?? 0}%)`
                      : 'UNAVAILABLE',
                  data: sparkHistory,
                  dataKey: 'hostMemPct' as const,
                  stroke: '#6c79c4',
                  isPct: true,
                },
                {
                  key: 'slots' as const,
                  title: 'Active & Queued Slots',
                  line1: `${latestSlot.running} / ${latestSlot.slots} (${latestSlot.queued} queued)`,
                  data: slotChartHistory,
                  dataKey: 'running' as const,
                  stroke: '#1d8cf8',
                  isPct: false,
                },
                {
                  key: 'ebpf' as const,
                  title: 'eBPF Signal Throughput',
                  line1: `${formatBytesCompact(totalEbpfIoBytes + totalEbpfSockBytes)} · ${totalEbpfOps} ops/t`,
                  data: sparkHistory,
                  dataKey: 'ebpfIoKib' as const,
                  stroke: '#e14eca',
                  isPct: false,
                },
                {
                  key: 'verdicts' as const,
                  title: 'Idle & Active Verdicts',
                  line1: `${verdictCounts.active} ACTIVE · ${verdictCounts.idle} IDLE`,
                  data: sparkHistory,
                  dataKey: 'activeVerdicts' as const,
                  stroke: '#00f2c3',
                  isPct: false,
                },
              ]
            ).map((item) => {
              const selected = perfTab === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setPerfTab(item.key)}
                  className={`w-full text-left flex items-center gap-3 px-2.5 py-2 rounded-md border transition cursor-pointer ${
                    selected
                      ? 'bg-[#3b6ea5]/20 border-[#3b6ea5]/60 text-white'
                      : 'bg-[#1e1e2f]/50 border-transparent hover:bg-[#1e1e2f] text-slate-300'
                  }`}
                >
                  <div className="w-14 h-10 rounded-sm border border-[#3b6ea5]/40 bg-[#1a1c2b] shrink-0 overflow-hidden pointer-events-none">
                    <AreaChart width={56} height={40} data={item.data} margin={{ top: 4, right: 0, left: 0, bottom: 4 }}>
                      <YAxis domain={item.isPct ? [0, 100] : [0, 'auto']} hide />
                      <Area
                        type="linear"
                        dataKey={item.dataKey}
                        stroke={item.stroke}
                        strokeWidth={1.3}
                        fill={item.stroke}
                        fillOpacity={0.22}
                        dot={false}
                        isAnimationActive={false}
                      />
                    </AreaChart>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-white truncate">{item.title}</p>
                    <p className="text-[11px] text-slate-300 font-mono truncate mt-0.5">{item.line1}</p>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Right Area: Selected View */}
          <div className="min-w-0 flex flex-col">
            <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
              <h3 className="text-xl font-medium text-white">
                {perfTab === 'cpu'
                  ? 'CPU'
                  : perfTab === 'memory'
                    ? 'Memory'
                    : perfTab === 'slots'
                      ? 'Active & Queued Slots'
                      : perfTab === 'ebpf'
                        ? 'eBPF Signal Throughput'
                        : 'Idle & Active Verdicts'}
              </h3>
              {perfSubtitleMap[perfTab] && (
                <span className="text-xs text-slate-300 font-mono truncate">{perfSubtitleMap[perfTab]}</span>
              )}
            </div>

            {(() => {
              const isPct = perfTab === 'cpu' || perfTab === 'memory';
              const isSlotTab = perfTab === 'slots';
              const activeData = isSlotTab ? slotChartHistory : chartHistory;
              const maxSlot = activeData.length - 1;
              const gridMod = isSlotTab ? 3 : 6;
              const readouts: Record<
                typeof perfTab,
                {
                  axisLeft: string;
                  axisRight: string;
                  metrics: Array<[string, string]>;
                  specs: Array<[string, string]>;
                }
              > = {
                cpu: {
                  axisLeft: '% Utilization',
                  axisRight: '100%',
                  metrics: [
                    ['Utilization', hostCpuVal != null ? `${hostCpuVal}%` : '—'],
                    ['Speed', hostSpeedGhz],
                    ['Avg Container', latestPoint?.avgContainerCpuPct != null ? `${latestPoint.avgContainerCpuPct}%` : '—'],
                    ['Processes', stats.host.procs_total != null ? String(stats.host.procs_total) : '—'],
                    ['Running Tasks', stats.host.procs_running != null ? String(stats.host.procs_running) : '—'],
                    ['Up time', formatUptime(stats.host.uptime_seconds)],
                  ],
                  specs: [
                    ['Logical processors', String(stats.host.logical_cpus ?? '—')],
                    ['CPU budget', `${(stats.reserved.cpu_millis / 1000).toFixed(1)} / ${(stats.budget.cpu_millis / 1000).toFixed(1)} cores`],
                    ['Active containers', `${stats.counts.RUNNING ?? 0} / ${stats.budget.slots}`],
                    ['eBPF probes', String(stats.observability?.ebpf.probes.length ?? 0)],
                    ['Tracked cgroups', String(stats.observability?.ebpf.tracked_cgroups.length ?? 0)],
                    ['Cgroup version', 'v2 (cgroupfs)'],
                  ],
                },
                memory: {
                  axisLeft: 'Memory usage',
                  axisRight: '100%',
                  metrics: [
                    ['In use', hostMemUsed != null ? formatBytesToGib(hostMemUsed) : '—'],
                    ['Utilization', hostMemPctVal != null ? `${hostMemPctVal}%` : '—'],
                    ['Available', hostMemFree != null ? formatBytesToGib(hostMemFree) : '—'],
                    ['Total RAM', hostMemTotal != null ? formatBytesToGib(hostMemTotal) : '—'],
                    ['Reserved', `${stats.reserved.memory_mib} MiB`],
                    ['Lab budget', `${stats.budget.memory_mib} MiB`],
                  ],
                  specs: [
                    ['Active containers', `${stats.counts.RUNNING ?? 0} / ${stats.budget.slots}`],
                    ['FIFO queued', String(stats.counts.QUEUED ?? 0)],
                    ['Mem source', '/proc/meminfo & cgroup v2'],
                    ['eBPF status', stats.observability?.ebpf.status ?? 'UNAVAILABLE'],
                    ['Ringbuf loss', String(stats.observability?.ebpf.loss_count ?? 0)],
                    ['Kernel', stats.host.kernel_release ?? '—'],
                  ],
                },
                slots: {
                  axisLeft: 'Active & Queued Slots',
                  axisRight: `Cap ${stats.budget.slots} slots`,
                  metrics: [
                    ['Running slots', `${latestSlot.running} / ${latestSlot.slots}`],
                    ['FIFO queued', String(latestSlot.queued)],
                    ['Provisioning', String(stats.counts.PROVISIONING ?? 0)],
                    ['Reserved CPU', `${(stats.reserved.cpu_millis / 1000).toFixed(1)} cores`],
                    ['Reserved RAM', `${stats.reserved.memory_mib} MiB`],
                    ['Total sessions', String(stats.sessions.length)],
                  ],
                  specs: [
                    ['Sample cadence', '10s interval (3m window)'],
                    ['Last sample', formatShortTime(latestSlot.sampledAt)],
                    ['CPU budget', `${(stats.budget.cpu_millis / 1000).toFixed(1)} cores`],
                    ['RAM budget', `${stats.budget.memory_mib} MiB`],
                    ['Demo state', stats.demo?.state ?? 'idle'],
                    ['Demo active', String(stats.demo?.active_demo_sessions ?? 0)],
                  ],
                },
                ebpf: {
                  axisLeft: 'Throughput (KiB/s)',
                  axisRight: 'Dynamic',
                  metrics: [
                    ['VFS I/O rate', `${(latestPoint?.ebpfIoKib ?? 0).toFixed(1)} KiB/s`],
                    ['Socket I/O rate', `${(latestPoint?.ebpfSockKib ?? 0).toFixed(1)} KiB/s`],
                    ['Ops / tick', `${totalEbpfOps}`],
                    ['Total VFS', formatBytesCompact(totalEbpfIoBytes)],
                    ['Total Socket', formatBytesCompact(totalEbpfSockBytes)],
                    ['Ringbuf loss', String(stats.observability?.ebpf.loss_count ?? 0)],
                  ],
                  specs: [
                    ['Collector state', stats.observability?.ebpf.status ?? 'UNAVAILABLE'],
                    ['Attached probes', String(stats.observability?.ebpf.probes.length ?? 0)],
                    ['Tracked cgroups', String(stats.observability?.ebpf.tracked_cgroups.length ?? 0)],
                    ['Sample time', formatShortTime(stats.sampled_at)],
                    ['Top target', ebpfBarData[0] ? `${ebpfBarData[0].name} (${ebpfBarData[0].kibPerSec} KiB/s)` : 'idle / 0 B'],
                    ['Kernel', stats.host.kernel_release ?? '—'],
                  ],
                },
                verdicts: {
                  axisLeft: 'Container Verdicts',
                  axisRight: 'Dynamic',
                  metrics: [
                    ['ACTIVE', String(verdictCounts.active)],
                    ['IDLE candidates', String(verdictCounts.idle)],
                    ['UNKNOWN', String(verdictCounts.unknown)],
                    ['Running total', String(runningSessions.length)],
                    ['Quiet cutoff', `${stats.observability?.thresholds.idle_quiet_seconds ?? '—'}s`],
                    ['Interaction grace', `${stats.observability?.thresholds.interaction_grace_seconds ?? '—'}s`],
                  ],
                  specs: [
                    ['Policy mode', stats.observability?.read_only ? 'Advisory (read-only)' : 'Active'],
                    ['CPU threshold', `< ${stats.observability?.thresholds.idle_cpu_threshold_pct ?? '—'}%`],
                    ['Stale cutoff', `${stats.observability?.thresholds.stale_threshold_seconds ?? '—'}s`],
                    ['eBPF gate', stats.observability?.ebpf.status ?? 'UNAVAILABLE'],
                    ['FIFO queued', String(stats.counts.QUEUED ?? 0)],
                    ['Completed', String((stats.counts.RELEASED ?? 0) + (stats.counts.COMPLETED ?? 0))],
                  ],
                },
              };
              const current = readouts[perfTab];

              return (
                <div className="flex flex-col">
                  {/* Full-Width Windows 11 Task Manager Graph */}
                  <div className="flex items-center justify-between text-[11px] text-[#9a9a9a] mb-1">
                    <span>{current.axisLeft}</span>
                    <span>{current.axisRight}</span>
                  </div>

                  <div className="w-full h-[265px] rounded-sm border border-[#3b6ea5]/50 bg-[#1a1c2b]">
                    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                      <AreaChart data={activeData} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
                        <defs>
                          <linearGradient id="taskMgrFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="rgba(74, 133, 197, 0.24)" />
                            <stop offset="100%" stopColor="rgba(74, 133, 197, 0.02)" />
                          </linearGradient>
                          <linearGradient id="ebpfMgrFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="rgba(225, 78, 202, 0.22)" />
                            <stop offset="100%" stopColor="rgba(225, 78, 202, 0.02)" />
                          </linearGradient>
                          <linearGradient id="verdictMgrFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="rgba(0, 242, 195, 0.22)" />
                            <stop offset="100%" stopColor="rgba(0, 242, 195, 0.02)" />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="rgba(255, 255, 255, 0.07)" vertical={false} horizontal={true} />
                        <XAxis dataKey="slot" type="number" domain={[0, maxSlot]} hide />
                        <YAxis
                          width={0}
                          tick={false}
                          axisLine={false}
                          tickLine={false}
                          domain={isPct ? [0, 100] : [0, 'auto']}
                          ticks={isPct ? [0, 20, 40, 60, 80, 100] : undefined}
                        />
                        {activeData
                          .filter((pt) => pt.seq % gridMod === 0)
                          .map((pt) => (
                            <ReferenceLine
                              key={pt.seq}
                              x={pt.slot}
                              stroke="rgba(255, 255, 255, 0.09)"
                              strokeWidth={1}
                              ifOverflow="hidden"
                            />
                          ))}
                        <Tooltip
                          labelFormatter={(_, payload) => {
                            const ts = payload?.[0]?.payload?.sampledAt as string | undefined;
                            return ts ? `${formatShortTime(ts)} UTC` : 'Baseline window';
                          }}
                          contentStyle={{
                            backgroundColor: '#1e1e2f',
                            border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: 8,
                            fontSize: 12,
                            color: '#fff',
                          }}
                        />
                        {perfTab === 'cpu' && (
                          <>
                            <Area
                              type="linear"
                              dataKey="hostCpuPct"
                              name="Host CPU %"
                              stroke="#4a85c5"
                              strokeWidth={1.5}
                              fill="url(#taskMgrFill)"
                              dot={false}
                              activeDot={{ r: 3 }}
                              isAnimationActive={false}
                              connectNulls={false}
                            />
                            <Area
                              type="linear"
                              dataKey="avgContainerCpuPct"
                              name="Avg Container CPU %"
                              stroke="#5bb397"
                              strokeWidth={1.5}
                              fill="none"
                              dot={false}
                              activeDot={{ r: 3 }}
                              isAnimationActive={false}
                              connectNulls={false}
                            />
                          </>
                        )}
                        {perfTab === 'memory' && (
                          <Area
                            type="linear"
                            dataKey="hostMemPct"
                            name="Host Memory %"
                            stroke="#6c79c4"
                            strokeWidth={1.5}
                            fill="url(#taskMgrFill)"
                            dot={false}
                            activeDot={{ r: 3 }}
                            isAnimationActive={false}
                            connectNulls={false}
                          />
                        )}
                        {perfTab === 'slots' && (
                          <>
                            <Area
                              type="linear"
                              dataKey="running"
                              name="Running Slots"
                              stroke="#1d8cf8"
                              strokeWidth={1.5}
                              fill="url(#taskMgrFill)"
                              dot={false}
                              activeDot={{ r: 3 }}
                              isAnimationActive={false}
                            />
                            <Area
                              type="linear"
                              dataKey="queued"
                              name="FIFO Queued"
                              stroke="#ff8d72"
                              strokeWidth={1.5}
                              fill="none"
                              dot={false}
                              activeDot={{ r: 3 }}
                              isAnimationActive={false}
                            />
                          </>
                        )}
                        {perfTab === 'ebpf' && (
                          <>
                            <Area
                              type="linear"
                              dataKey="ebpfIoKib"
                              name="VFS I/O (KiB/s)"
                              stroke="#e14eca"
                              strokeWidth={1.5}
                              fill="url(#ebpfMgrFill)"
                              dot={false}
                              activeDot={{ r: 3 }}
                              isAnimationActive={false}
                            />
                            <Area
                              type="linear"
                              dataKey="ebpfSockKib"
                              name="Socket I/O (KiB/s)"
                              stroke="#4a85c5"
                              strokeWidth={1.5}
                              fill="none"
                              dot={false}
                              activeDot={{ r: 3 }}
                              isAnimationActive={false}
                            />
                          </>
                        )}
                        {perfTab === 'verdicts' && (
                          <>
                            <Area
                              type="linear"
                              dataKey="activeVerdicts"
                              name="ACTIVE"
                              stroke="#00f2c3"
                              strokeWidth={1.5}
                              fill="url(#verdictMgrFill)"
                              dot={false}
                              activeDot={{ r: 3 }}
                              isAnimationActive={false}
                            />
                            <Area
                              type="linear"
                              dataKey="idleVerdicts"
                              name="IDLE_CANDIDATE"
                              stroke="#e14eca"
                              strokeWidth={1.5}
                              fill="none"
                              dot={false}
                              activeDot={{ r: 3 }}
                              isAnimationActive={false}
                            />
                          </>
                        )}
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-[#9a9a9a] mt-1">
                    <span>{isSlotTab ? '180 seconds' : '60 seconds'}</span>
                    <span>0</span>
                  </div>

                  {/* Windows 11 Task Manager Metrics & Specs Footer */}
                  <div className="flex flex-wrap items-start gap-x-10 gap-y-4 mt-4">
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-7 gap-y-2.5">
                      {current.metrics.map(([label, val]) => (
                        <div key={label} className="min-w-0">
                          <p className="text-[11px] text-[#9a9a9a] truncate">{label}</p>
                          <p className="text-lg font-light text-white font-mono truncate">{val}</p>
                        </div>
                      ))}
                    </div>

                    <div className="grid grid-cols-[135px_auto] gap-x-5 gap-y-1 text-xs content-start">
                      {current.specs.map(([label, val]) => (
                        <div key={label} className="contents">
                          <span className="text-[#9a9a9a]">{label}:</span>
                          <span className="text-slate-200 font-mono truncate">{val}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      </div>

      {/* Row 3: Bottom 2-Column Split Grid ("Tasks / Idle Verdicts" + "Simple Table") */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Card: Tasks / Live Idle Checklist */}
        <div className="lg:col-span-5 bg-[#27293d] rounded-lg p-5 shadow-lg border border-white/5 flex flex-col gap-4">
          <div className="flex items-center justify-between gap-2 border-b border-gray-700/50 pb-3">
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-white">
                IDLE CHECKS ({taskSessions.length})
              </span>
              <span className="text-xs text-[#9a9a9a]">Read-only eBPF</span>
            </div>
            <div className="flex items-center gap-2">
              <Filter className="w-3.5 h-3.5 text-[#9a9a9a]" />
              <select
                aria-label="Filter idle checks"
                value={taskFilter}
                onChange={(e) => setTaskFilter(e.target.value as 'ALL' | RecommendationDecision)}
                className="bg-[#1e1e2f] border border-white/10 rounded px-2 py-1 text-[11px] text-white focus:outline-none focus:border-[#1d8cf8]"
              >
                <option value="ALL">ALL</option>
                <option value="IDLE_CANDIDATE">IDLE_CANDIDATE</option>
                <option value="ACTIVE">ACTIVE</option>
                <option value="UNKNOWN">UNKNOWN</option>
              </select>
            </div>
          </div>

          {taskSessions.length === 0 ? (
            <div className="py-8 text-center space-y-3">
              <p className="text-xs text-[#9a9a9a]">No running containers to inspect right now.</p>
              <button
                type="button"
                onClick={() => onNavigate('demo')}
                className="px-3 py-1.5 rounded bg-gradient-to-r from-[#1d8cf8] to-[#3358f4] text-white text-xs font-semibold cursor-pointer"
              >
                Launch Demo Scenario
              </button>
            </div>
          ) : (
            <div className="divide-y divide-gray-700/50 max-h-[300px] overflow-y-auto pr-1">
              {taskSessions.map((s) => {
                const sample = stats.containers?.[s.id];
                const rec = sample?.recommendation;
                const owner = stats.owner_names[s.owner] ?? s.owner;
                const checked = Boolean(acknowledgedTasks[s.id]);
                const demoRole = stats.demo?.session_roles?.[s.id];
                return (
                  <div key={s.id} className="py-3 flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <button
                        type="button"
                        aria-label={`Acknowledge ${s.id}`}
                        onClick={() => setAcknowledgedTasks((prev) => ({ ...prev, [s.id]: !prev[s.id] }))}
                        className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 cursor-pointer transition ${
                          checked
                            ? 'bg-[#e14eca] border-[#e14eca] text-white'
                            : 'border-[#9a9a9a]/50 hover:border-[#1d8cf8]'
                        }`}
                      >
                        {checked && <span className="text-[10px] leading-none font-bold">&#10003;</span>}
                      </button>
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs font-semibold text-white">
                            {owner} &middot; {s.id.slice(0, 8)}
                          </span>
                          {getRecommendationBadge(rec?.decision)}
                          {demoRole && (
                            <span className="text-[10px] font-mono text-[#1d8cf8]">[{demoRole}]</span>
                          )}
                        </div>
                        <p className="text-[11px] text-[#9a9a9a] mt-1 leading-snug">
                          {rec?.reason ?? 'Awaiting telemetry'}
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      title="Inspect container signals"
                      onClick={() => setSelectedSessionId(s.id)}
                      className="p-1.5 rounded text-[#9a9a9a] hover:text-[#1d8cf8] hover:bg-white/5 cursor-pointer shrink-0"
                    >
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Card: Simple Table */}
        <div className="lg:col-span-7 bg-[#27293d] rounded-lg p-5 shadow-lg border border-white/5 flex flex-col gap-3">
          <div className="flex items-center justify-between border-b border-gray-700/50 pb-3">
            <div>
              <h3 className="text-sm font-semibold text-white">Sessions &amp; eBPF Table</h3>
              <p className="text-[11px] text-[#9a9a9a]">Click any row to inspect full kernel telemetry</p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate('tables')}
              className="text-xs text-[#1d8cf8] hover:underline cursor-pointer"
            >
              Expand all ({sortedSessions.length})
            </button>
          </div>

          {filteredSessions.length === 0 ? (
            <p className="text-xs text-[#9a9a9a] py-8 text-center">No sessions submitted yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-gray-700/50 text-[11px] uppercase tracking-wider text-[#9a9a9a]">
                    <th className="py-2.5 px-2">Owner / ID</th>
                    <th className="py-2.5 px-2">State</th>
                    <th className="py-2.5 px-2">CPU · RAM</th>
                    <th className="py-2.5 px-2">eBPF I/O · Sock · Exec</th>
                    <th className="py-2.5 px-2 text-right">Verdict</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700/50">
                  {filteredSessions.slice(0, 8).map((s) => {
                    const sample: ContainerSample | undefined = stats.containers?.[s.id];
                    const cpuRatePct = sample?.signals?.cpu_pct ?? containerCpuRates[s.id];
                    return (
                      <tr
                        key={s.id}
                        onClick={() => setSelectedSessionId(s.id)}
                        className={`cursor-pointer transition ${
                          selectedSession?.id === s.id ? 'bg-[#1d8cf8]/10' : 'hover:bg-white/5'
                        }`}
                      >
                        <td className="py-2.5 px-2">
                          <div className="font-medium text-white">{stats.owner_names[s.owner] ?? s.owner}</div>
                          <div className="font-mono text-[10px] text-[#9a9a9a]">{s.id.slice(0, 10)}</div>
                        </td>
                        <td className="py-2.5 px-2">{getStateBadge(s.state, s.queue_position)}</td>
                        <td className="py-2.5 px-2 font-mono text-slate-200">
                          {s.state === 'RUNNING'
                            ? `${cpuRatePct != null ? cpuRatePct.toFixed(1) + '%' : '—'} · ${formatBytesToMib(sample?.memory_usage_bytes)}`
                            : `${s.cpu_millis}m`}
                        </td>
                        <td className="py-2.5 px-2 font-mono text-[#9a9a9a]">
                          {sample?.signals
                            ? `IO ${sample.signals.io_events_delta ?? 0} · Sock ${sample.signals.socket_events_delta ?? 0} · Exec ${sample.signals.exec_events_delta ?? 0}`
                            : '—'}
                        </td>
                        <td className="py-2.5 px-2 text-right">
                          {s.state === 'RUNNING' ? getRecommendationBadge(sample?.recommendation?.decision) : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {sessionDetailPanel}
    </div>
  );
}
