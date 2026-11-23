export type SessionState =
  | 'REQUESTED'
  | 'QUEUED'
  | 'PROVISIONING'
  | 'RUNNING'
  | 'RELEASING'
  | 'COMPLETED'
  | 'RELEASED'
  | 'FAILED'
  | 'CANCELLED';

export interface LifecycleEvent {
  state: SessionState;
  at: string;
}

export interface Session {
  id: string;
  owner: string;
  cpu_millis: number;
  memory_mib: number;
  state: SessionState;
  created_at: string;
  events: LifecycleEvent[];
  container_id?: string | null;
  failure?: string | null;
  cleanup_pending: boolean;
  queue_position?: number | null;
  queue_seconds?: number | null;
  provisioning_seconds?: number | null;
}

export interface RequestPayload {
  cpu_millis?: number;
  memory_mib?: number;
}

export interface CapacityBlock {
  cpu_millis: number;
  memory_mib: number;
  slots: number;
}

export interface HostTelemetry {
  available: boolean;
  cpu_total_ticks?: number;
  cpu_idle_ticks?: number;
  cpu_utilization_pct?: number | null;
  memory_total_bytes?: number;
  memory_used_bytes?: number;
  cpu_model?: string | null;
  cpu_mhz?: number | null;
  logical_cpus?: number | null;
  uptime_seconds?: number | null;
  procs_running?: number | null;
  procs_total?: number | null;
  kernel_release?: string | null;
  sampled_at?: string;
}

export type QualityStatus = 'OK' | 'STALE' | 'DEGRADED' | 'UNAVAILABLE';
export type RecommendationDecision = 'ACTIVE' | 'IDLE_CANDIDATE' | 'UNKNOWN';

export interface SessionSignals {
  cgroup_id?: number | null;
  cpu_pct?: number | null;
  memory_bytes?: number | null;
  blk_read_bytes?: number | null;
  blk_write_bytes?: number | null;
  io_read_bytes_total?: number | null;
  io_write_bytes_total?: number | null;
  io_read_bytes_per_sec?: number | null;
  io_write_bytes_per_sec?: number | null;
  io_events_delta?: number | null;
  sock_rx_bytes_total?: number | null;
  sock_tx_bytes_total?: number | null;
  sock_rx_bytes_per_sec?: number | null;
  sock_tx_bytes_per_sec?: number | null;
  socket_events_delta?: number | null;
  exec_events_delta?: number | null;
  fork_events_delta?: number | null;
  exit_events_delta?: number | null;
  recent_comm?: string | null;
  psi_cpu_some_avg10?: number | null;
  psi_io_some_avg10?: number | null;
  last_interaction_at?: string | null;
  last_interaction_source?: string | null;
  interaction_age_seconds?: number | null;
  sample_time?: string;
}

export interface SignalQuality {
  status: QualityStatus;
  ebpf_status: string;
  freshness_seconds?: number | null;
  loss_delta?: number | null;
  missing: string[];
  reason: string;
}

export interface SessionRecommendation {
  decision: RecommendationDecision;
  confidence: string;
  quiet_seconds: number;
  reason: string;
  read_only: boolean;
}

export interface SignalHistoryPoint {
  sampled_at: string;
  cpu_pct: number | null;
  memory_bytes: number | null;
  io_events: number | null;
  socket_events: number | null;
  exec_events: number | null;
  decision: RecommendationDecision;
}

export interface ContainerSample {
  available: boolean;
  cpu_usage_ns?: number | null;
  memory_usage_bytes?: number | null;
  sampled_at: string;
  signals?: SessionSignals;
  signal_quality?: SignalQuality;
  recommendation?: SessionRecommendation;
  history?: SignalHistoryPoint[];
}

export interface ObservabilitySummary {
  read_only: boolean;
  ebpf: {
    enabled: boolean;
    status: string;
    reason: string;
    probes: string[];
    loss_count?: number | null;
    last_snapshot_at?: string | null;
    tracked_cgroups: number[];
  };
  thresholds: {
    idle_cpu_threshold_pct: number;
    idle_quiet_seconds: number;
    interaction_grace_seconds: number;
    stale_threshold_seconds: number;
  };
}

export interface DemoScenarioSpec {
  id: string;
  title: string;
  description: string;
  requests: number;
  duration_seconds: number;
}

export interface DemoStatus {
  state: string;
  scenario?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  total_submitted: number;
  active_demo_sessions: number;
  completed_count: number;
  message: string;
  session_roles: Record<string, string>;
  scenarios: DemoScenarioSpec[];
}

export interface AdminStats {
  sampled_at: string;
  accounts: { total: number; active: number };
  owner_names: Record<string, string>;
  queue_reasons: Record<string, string[]>;
  total_sessions: number;
  counts: Record<SessionState, number>;
  queue: string[];
  sessions: Session[];
  headroom: {
    cpu_millis: number;
    memory_mib: number;
  };
  budget: CapacityBlock;
  reserved: CapacityBlock;
  available: CapacityBlock;
  host: HostTelemetry;
  active_containers: number | null;
  containers: Record<string, ContainerSample> | null;
  observability?: ObservabilitySummary;
  demo?: DemoStatus;
}

