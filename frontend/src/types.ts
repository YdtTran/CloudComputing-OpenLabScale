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
