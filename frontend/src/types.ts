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
  sampled_at?: string;
}

export interface ContainerSample {
  available: boolean;
  cpu_usage_ns?: number | null;
  memory_usage_bytes?: number | null;
  sampled_at: string;
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
}

