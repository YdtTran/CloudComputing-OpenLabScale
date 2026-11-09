import type { AdminStats, RequestPayload, Session } from './types';

function headers(token: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };
}

export async function submitSession(token: string, payload: RequestPayload = {}): Promise<Session> {
  const res = await fetch('/sessions', {
    method: 'POST',
    headers: headers(token),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Failed to submit session (${res.status})`);
  }
  return res.json();
}

export async function getSession(token: string, sessionId: string): Promise<Session> {
  const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}`, {
    headers: headers(token),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Failed to get session (${res.status})`);
  }
  return res.json();
}

export async function listSessions(token: string): Promise<Session[]> {
  const res = await fetch('/sessions', {
    headers: headers(token),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Failed to list sessions (${res.status})`);
  }
  return res.json();
}

export async function releaseSession(token: string, sessionId: string): Promise<Session> {
  const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: headers(token),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Failed to release session (${res.status})`);
  }
  return res.json();
}

export async function getStats(token: string): Promise<AdminStats> {
  const res = await fetch('/stats', {
    headers: headers(token),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(`HTTP ${res.status}: ${errorData.detail || res.statusText}`);
  }
  return res.json();
}

