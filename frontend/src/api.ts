import type { AdminStats, DemoStatus, RequestPayload, Session } from './types';

async function apiFetch<T>(url: string, token: string, init: RequestInit = {}, label = 'Request'): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': token,
      ...init.headers,
    },
  });
  if (!res.ok) {
    if (res.status === 401) window.dispatchEvent(new Event('session-expired'));
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(`HTTP ${res.status}: ${errorData.detail || `${label} failed`}`);
  }
  return res.json();
}

export function submitSession(token: string, payload: RequestPayload = {}): Promise<Session> {
  return apiFetch('/sessions', token, { method: 'POST', body: JSON.stringify(payload) }, 'Submit session');
}

export function getSession(token: string, sessionId: string, signal?: AbortSignal): Promise<Session> {
  return apiFetch(`/sessions/${encodeURIComponent(sessionId)}`, token, { signal }, 'Get session');
}

export function listSessions(token: string, signal?: AbortSignal): Promise<Session[]> {
  return apiFetch('/sessions', token, { signal }, 'List sessions');
}

export function releaseSession(token: string, sessionId: string): Promise<Session> {
  return apiFetch(`/sessions/${encodeURIComponent(sessionId)}`, token, { method: 'DELETE' }, 'Release session');
}

export function getStats(token: string, signal?: AbortSignal): Promise<AdminStats> {
  return apiFetch('/stats', token, { signal }, 'Get stats');
}

export function runDemoScenario(token: string, scenario: string): Promise<DemoStatus> {
  return apiFetch('/admin/demo/run', token, { method: 'POST', body: JSON.stringify({ scenario }) }, 'Launch demo');
}

export function stopDemoScenario(token: string): Promise<DemoStatus> {
  return apiFetch('/admin/demo/stop', token, { method: 'POST' }, 'Stop demo');
}
