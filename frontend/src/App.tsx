import { useEffect, useState, useCallback } from 'react';
import {
  Cpu,
  Database,
  Layers,
  Play,
  Square,
  RefreshCw,
  Clock,
  User,
  ShieldAlert,
  Server,
  Activity,
  CheckCircle2,
  Lock,
} from 'lucide-react';
import { submitSession, getSession, listSessions, releaseSession } from './api';
import type { Session, SessionState } from './types';
import { TerminalView } from './components/TerminalView';

const DEMO_IDENTITIES = [
  { id: 'alice', label: 'Alice (Student 1)', token: 'token-alice' },
  { id: 'bob', label: 'Bob (Student 2)', token: 'token-bob' },
];

export function App() {
  const [selectedIdentity, setSelectedIdentity] = useState(DEMO_IDENTITIES[0]);
  const [customToken, setCustomToken] = useState('');
  const [isCustom, setIsCustom] = useState(false);

  const activeToken = isCustom ? customToken.trim() : selectedIdentity.token;

  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [forcedTerminalSessionId, setForcedTerminalSessionId] = useState<string | null>(null);
  const [lookupId, setLookupId] = useState('');
  const [sessionList, setSessionList] = useState<Session[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [releasing, setReleasing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [cpuMillis, setCpuMillis] = useState<number>(500);
  const [memoryMib, setMemoryMib] = useState<number>(256);
  const [uptimeSeconds, setUptimeSeconds] = useState<number>(0);

  const switchIdentity = (nextCustom: boolean, nextIdentity = selectedIdentity) => {
    setIsCustom(nextCustom);
    setSelectedIdentity(nextIdentity);
    setActiveSession(null);
    setForcedTerminalSessionId(null);
    setSessionList([]);
    setError(null);
    setUptimeSeconds(0);
  };

  const fetchSessions = useCallback(async () => {
    if (!activeToken) return;
    try {
      const list = await listSessions(activeToken);
      setSessionList(list);
      setActiveSession((prev) => {
        if (prev) {
          const match = list.find((s) => s.id === prev.id);
          return match ?? prev;
        }
        return list.find((s) => ['REQUESTED', 'QUEUED', 'PROVISIONING', 'RUNNING', 'RELEASING'].includes(s.state)) ?? list[0] ?? null;
      });
    } catch (err: unknown) {
      if (err instanceof Error && err.message.includes('401')) {
        setError('Invalid demo token (HTTP 401).');
      }
    }
  }, [activeToken]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Poll active session while in non-terminal lifecycle states or cleanup_pending
  useEffect(() => {
    if (!activeSession || !activeToken) return;
    const doneStates: SessionState[] = ['COMPLETED', 'RELEASED', 'FAILED', 'CANCELLED'];
    if (doneStates.includes(activeSession.state) && !activeSession.cleanup_pending) return;

    const interval = setInterval(async () => {
      try {
        const updated = await getSession(activeToken, activeSession.id);
        setActiveSession(updated);
        listSessions(activeToken).then(setSessionList).catch(() => {});
      } catch (err: unknown) {
        if (err instanceof Error && err.message.includes('404')) {
          setActiveSession(null);
        }
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [activeSession, activeToken]);

  // Live duration ticker for RUNNING session
  useEffect(() => {
    if (!activeSession || activeSession.state !== 'RUNNING') {
      setUptimeSeconds(0);
      return;
    }
    const runningEvent = activeSession.events.find((e) => e.state === 'RUNNING');
    const startTime = runningEvent
      ? new Date(runningEvent.at).getTime()
      : new Date(activeSession.created_at).getTime();

    const updateElapsed = () => {
      setUptimeSeconds(Math.max(0, Math.floor((Date.now() - startTime) / 1000)));
    };
    updateElapsed();
    const timer = setInterval(updateElapsed, 1000);
    return () => clearInterval(timer);
  }, [activeSession]);

  const handleRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeToken) {
      setError('Please select or enter a demo token.');
      return;
    }
    setError(null);
    setForcedTerminalSessionId(null);
    setSubmitting(true);
    try {
      const session = await submitSession(activeToken, {
        cpu_millis: cpuMillis,
        memory_mib: memoryMib,
      });
      setActiveSession(session);
      await fetchSessions();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to request container');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRelease = async () => {
    if (!activeSession || !activeToken) return;
    setReleasing(true);
    setError(null);
    try {
      const updated = await releaseSession(activeToken, activeSession.id);
      setActiveSession(updated);
      setForcedTerminalSessionId(null);
      await fetchSessions();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to release container');
    } finally {
      setReleasing(false);
    }
  };

  const handleLookupSession = async (e: React.FormEvent) => {
    e.preventDefault();
    const targetId = lookupId.trim();
    if (!targetId || !activeToken) return;
    setError(null);
    try {
      const found = await getSession(activeToken, targetId);
      setActiveSession(found);
      setForcedTerminalSessionId(null);
    } catch (err: unknown) {
      // Also allow testing WebSocket cross-session rejection directly
      setError(
        `${err instanceof Error ? err.message : 'Access denied'} — Opening WebSocket terminal for "${targetId.slice(0, 8)}" to verify cross-session block...`,
      );
      setForcedTerminalSessionId(targetId);
    }
  };

  const formatSeconds = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const getStateBadge = (state: SessionState, queuePos?: number | null) => {
    switch (state) {
      case 'RUNNING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            RUNNING
          </span>
        );
      case 'PROVISIONING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/30">
            <RefreshCw className="w-3 h-3 animate-spin" />
            PROVISIONING
          </span>
        );
      case 'REQUESTED':
      case 'QUEUED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
            <Clock className="w-3 h-3" />
            {state} {queuePos ? `(#${queuePos})` : ''}
          </span>
        );
      case 'RELEASING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/30">
            <RefreshCw className="w-3 h-3 animate-spin" />
            RELEASING
          </span>
        );
      case 'RELEASED':
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">
            <CheckCircle2 className="w-3 h-3" />
            {state}
          </span>
        );
      case 'FAILED':
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <ShieldAlert className="w-3 h-3" />
            {state}
          </span>
        );
    }
  };

  const hasActiveRunningOrWaiting = Boolean(
    activeSession && ['REQUESTED', 'QUEUED', 'PROVISIONING', 'RUNNING', 'RELEASING'].includes(activeSession.state),
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-sky-500/10 border border-sky-500/20 rounded-lg text-sky-400">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h1 className="font-bold text-base tracking-tight text-white flex items-center gap-2">
                OpenLabScale
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 bg-sky-500/20 text-sky-300 rounded border border-sky-500/30">
                  Student Portal
                </span>
              </h1>
              <p className="text-xs text-slate-400">Isolated Linux Containers on Single-Host Scheduler</p>
            </div>
          </div>

          <div className="flex items-center gap-2 bg-slate-800/80 p-1.5 rounded-lg border border-slate-700">
            <span
              className="hidden sm:inline-flex items-center gap-1 text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30"
              title="Static bearer token for classroom demo only; not production authentication"
            >
              Demo Identity (Not Secure Auth)
            </span>
            <div className="flex items-center gap-1 text-xs text-slate-300 px-1.5 font-medium">
              <User className="w-3.5 h-3.5 text-sky-400" />
            </div>
            <select
              className="bg-slate-900 border border-slate-700 text-xs rounded px-2.5 py-1 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
              value={isCustom ? 'custom' : selectedIdentity.id}
              onChange={(e) => {
                if (e.target.value === 'custom') {
                  switchIdentity(true);
                } else {
                  const found = DEMO_IDENTITIES.find((id) => id.id === e.target.value);
                  if (found) switchIdentity(false, found);
                }
              }}
            >
              {DEMO_IDENTITIES.map((id) => (
                <option key={id.id} value={id.id}>
                  {id.label}
                </option>
              ))}
              <option value="custom">Custom Token...</option>
            </select>

            {isCustom && (
              <input
                type="text"
                placeholder="Token..."
                value={customToken}
                onChange={(e) => {
                  setCustomToken(e.target.value);
                  setActiveSession(null);
                  setForcedTerminalSessionId(null);
                }}
                className="bg-slate-900 border border-slate-700 text-xs rounded px-2 py-1 w-28 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500 font-mono"
              />
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full flex flex-col gap-6">
        {error && (
          <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-300 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{error}</span>
            </div>
            <button
              onClick={() => setError(null)}
              className="text-xs text-rose-400 hover:text-rose-200 underline ml-4 cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1">
          <div className="lg:col-span-4 flex flex-col gap-5">
            {/* Request Container Form */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-200 mb-1 flex items-center gap-2">
                <Play className="w-4 h-4 text-sky-400" />
                Request New Environment
              </h2>
              <p className="text-xs text-slate-400 mb-4">
                Reserve an isolated Linux session on the single-host FIFO scheduler.
              </p>

              <form onSubmit={handleRequest} className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-slate-300 flex items-center justify-between mb-1">
                    <span className="flex items-center gap-1.5">
                      <Cpu className="w-3.5 h-3.5 text-sky-400" /> CPU Allocation
                    </span>
                    <span className="font-mono text-sky-400 font-semibold">
                      {cpuMillis} ms ({cpuMillis / 1000} vCPU)
                    </span>
                  </label>
                  <input
                    type="range"
                    min="100"
                    max="1500"
                    step="50"
                    value={cpuMillis}
                    onChange={(e) => setCpuMillis(Number(e.target.value))}
                    className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-sky-500"
                  />
                  <div className="flex justify-between text-[10px] text-slate-500 mt-0.5">
                    <span>100 ms</span>
                    <span>Default: 500 ms</span>
                    <span>1500 ms</span>
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-slate-300 flex items-center justify-between mb-1">
                    <span className="flex items-center gap-1.5">
                      <Database className="w-3.5 h-3.5 text-sky-400" /> Memory Allocation
                    </span>
                    <span className="font-mono text-sky-400 font-semibold">{memoryMib} MiB</span>
                  </label>
                  <input
                    type="range"
                    min="64"
                    max="1024"
                    step="64"
                    value={memoryMib}
                    onChange={(e) => setMemoryMib(Number(e.target.value))}
                    className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-sky-500"
                  />
                  <div className="flex justify-between text-[10px] text-slate-500 mt-0.5">
                    <span>64 MiB</span>
                    <span>Default: 256 MiB</span>
                    <span>1024 MiB</span>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={submitting || hasActiveRunningOrWaiting}
                  className="w-full py-2.5 px-4 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-800 disabled:text-slate-500 text-white text-xs font-semibold rounded-lg shadow-sm transition flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
                >
                  {submitting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Submitting to FIFO Queue...
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5" />
                      Request Linux Container
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* Active Session Details & Live Metrics */}
            {activeSession && (
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-emerald-400" />
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                      Session Details
                    </span>
                  </div>
                  {getStateBadge(activeSession.state, activeSession.queue_position)}
                </div>

                <div className="space-y-1.5 text-xs">
                  <div className="flex justify-between py-1 border-b border-slate-800/80 gap-2">
                    <span className="text-slate-400 shrink-0">Session ID</span>
                    <span className="font-mono text-slate-200 select-all font-semibold truncate">
                      {activeSession.id}
                    </span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-800/80">
                    <span className="text-slate-400">Owner</span>
                    <span className="text-slate-200 font-medium">{activeSession.owner}</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-800/80">
                    <span className="text-slate-400">Resource Limits</span>
                    <span className="font-mono text-slate-200">
                      {activeSession.cpu_millis}m CPU / {activeSession.memory_mib}MiB RAM
                    </span>
                  </div>
                  {activeSession.container_id && (
                    <div className="flex justify-between py-1 border-b border-slate-800/80">
                      <span className="text-slate-400">Container ID</span>
                      <span className="font-mono text-slate-300">
                        {activeSession.container_id.slice(0, 12)}
                      </span>
                    </div>
                  )}
                  {activeSession.state === 'RUNNING' && (
                    <div className="flex justify-between py-1 border-b border-slate-800/80">
                      <span className="text-slate-400">Running Duration</span>
                      <span className="font-mono text-emerald-400 font-bold">
                        {formatSeconds(uptimeSeconds)}
                      </span>
                    </div>
                  )}
                  {activeSession.queue_position != null && (
                    <div className="flex justify-between py-1 border-b border-slate-800/80">
                      <span className="text-slate-400">Queue Position</span>
                      <span className="font-mono text-amber-400 font-bold">
                        #{activeSession.queue_position}
                      </span>
                    </div>
                  )}
                  {activeSession.queue_seconds != null && (
                    <div className="flex justify-between py-1 border-b border-slate-800/80">
                      <span className="text-slate-400">Queue Wait</span>
                      <span className="font-mono text-slate-300">
                        {activeSession.queue_seconds.toFixed(2)}s
                      </span>
                    </div>
                  )}
                  {activeSession.provisioning_seconds != null && (
                    <div className="flex justify-between py-1 border-b border-slate-800/80">
                      <span className="text-slate-400">Provision Time</span>
                      <span className="font-mono text-slate-300">
                        {activeSession.provisioning_seconds.toFixed(2)}s
                      </span>
                    </div>
                  )}
                  {activeSession.cleanup_pending && (
                    <div className="p-2 bg-amber-500/10 border border-amber-500/20 rounded text-amber-300 text-xs">
                      Cleanup retry pending on host Docker daemon.
                    </div>
                  )}
                  {activeSession.failure && (
                    <div className="p-2 bg-rose-500/10 border border-rose-500/20 rounded text-rose-300 text-xs">
                      Failure: {activeSession.failure}
                    </div>
                  )}
                </div>

                {['REQUESTED', 'QUEUED', 'PROVISIONING', 'RUNNING'].includes(activeSession.state) && (
                  <button
                    onClick={handleRelease}
                    disabled={releasing}
                    className="w-full py-2 px-3 bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 text-xs font-semibold rounded-lg transition flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {releasing ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        Releasing Session...
                      </>
                    ) : (
                      <>
                        <Square className="w-3.5 h-3.5" />
                        {activeSession.state === 'RUNNING'
                          ? 'Release & Cleanup Container'
                          : 'Cancel Session Request'}
                      </>
                    )}
                  </button>
                )}
              </div>
            )}

            {/* Session List & Cross-Session Access Test */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm flex-1 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-slate-400" />
                  Your Sessions ({sessionList.length})
                </span>
                <button
                  onClick={fetchSessions}
                  className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200 transition cursor-pointer"
                  title="Refresh sessions"
                >
                  <RefreshCw className="w-3 h-3" />
                </button>
              </div>

              {sessionList.length === 0 ? (
                <p className="text-xs text-slate-500 italic py-1">No sessions for this identity yet.</p>
              ) : (
                <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                  {sessionList.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => {
                        setForcedTerminalSessionId(null);
                        setActiveSession(s);
                      }}
                      className={`w-full text-left p-2 rounded-lg border text-xs transition flex items-center justify-between cursor-pointer ${
                        activeSession?.id === s.id && !forcedTerminalSessionId
                          ? 'bg-slate-800 border-sky-500/50 text-white'
                          : 'bg-slate-950/60 border-slate-800/80 text-slate-300 hover:bg-slate-800/50'
                      }`}
                    >
                      <div className="truncate font-mono">{s.id.slice(0, 10)}...</div>
                      <div className="shrink-0">{getStateBadge(s.state, s.queue_position)}</div>
                    </button>
                  ))}
                </div>
              )}

              <form onSubmit={handleLookupSession} className="pt-2 border-t border-slate-800/80 flex gap-1.5">
                <input
                  type="text"
                  placeholder="Open session ID (test isolation)..."
                  value={lookupId}
                  onChange={(e) => setLookupId(e.target.value)}
                  className="flex-1 bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs font-mono text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
                <button
                  type="submit"
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded border border-slate-700 transition flex items-center gap-1 cursor-pointer shrink-0"
                  title="Connect by Session ID (tests cross-session access block)"
                >
                  <Lock className="w-3 h-3 text-sky-400" />
                  Open
                </button>
              </form>
            </div>
          </div>

          {/* Right Column: Terminal or Lifecycle Status Screen */}
          <div className="lg:col-span-8 flex flex-col">
            {forcedTerminalSessionId ? (
              <TerminalView sessionId={forcedTerminalSessionId} token={activeToken} />
            ) : activeSession && activeSession.state === 'RUNNING' ? (
              <TerminalView sessionId={activeSession.id} token={activeToken} />
            ) : activeSession && ['REQUESTED', 'QUEUED'].includes(activeSession.state) ? (
              <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-8 flex flex-col items-center justify-center text-center">
                <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-full text-amber-400 mb-4 animate-bounce">
                  <Clock className="w-8 h-8" />
                </div>
                <h3 className="text-base font-semibold text-white mb-2">
                  Session Queued (FIFO Admission)
                </h3>
                <p className="text-xs text-slate-400 max-w-md mb-4">
                  Host capacity is currently reserved by other running containers. Your request is position{' '}
                  <span className="font-mono text-amber-400 font-bold">
                    #{activeSession.queue_position ?? 1}
                  </span>{' '}
                  in the admission queue. The terminal will attach automatically once capacity is freed.
                </p>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Polling admission status every second...
                </div>
              </div>
            ) : activeSession && activeSession.state === 'PROVISIONING' ? (
              <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-8 flex flex-col items-center justify-center text-center">
                <div className="p-4 bg-sky-500/10 border border-sky-500/20 rounded-full text-sky-400 mb-4 animate-spin">
                  <RefreshCw className="w-8 h-8" />
                </div>
                <h3 className="text-base font-semibold text-white mb-2">
                  Provisioning Isolated Container
                </h3>
                <p className="text-xs text-slate-400 max-w-md">
                  Configuring cgroup v2 CPU/RAM limits, non-root user (65534:65534), read-only rootfs, dropped capabilities, and attaching PTY shell...
                </p>
              </div>
            ) : activeSession && activeSession.state === 'RELEASING' ? (
              <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-8 flex flex-col items-center justify-center text-center">
                <div className="p-4 bg-purple-500/10 border border-purple-500/20 rounded-full text-purple-400 mb-4 animate-spin">
                  <RefreshCw className="w-8 h-8" />
                </div>
                <h3 className="text-base font-semibold text-white mb-2">
                  Releasing Session & Cleaning Up Container
                </h3>
                <p className="text-xs text-slate-400 max-w-md">
                  Stopping container and returning reserved CPU/memory capacity to the scheduler...
                </p>
              </div>
            ) : activeSession && ['RELEASED', 'COMPLETED', 'CANCELLED', 'FAILED'].includes(activeSession.state) ? (
              <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-8 flex flex-col items-center justify-center text-center">
                <div className="p-4 bg-slate-800 rounded-full text-slate-300 mb-4">
                  {activeSession.state === 'FAILED' ? (
                    <ShieldAlert className="w-8 h-8 text-rose-400" />
                  ) : (
                    <CheckCircle2 className="w-8 h-8 text-emerald-400" />
                  )}
                </div>
                <h3 className="text-base font-semibold text-white mb-1">
                  Session {activeSession.state}
                </h3>
                <p className="text-xs text-slate-400 max-w-md mb-4 font-mono">
                  id: {activeSession.id}
                </p>
                {activeSession.failure && (
                  <p className="text-xs text-rose-400 max-w-md mb-4">
                    Reason: {activeSession.failure}
                  </p>
                )}
                <p className="text-xs text-slate-500 max-w-sm">
                  Container resources have been reclaimed. Click &ldquo;Request Linux Container&rdquo; on the left to start a new session.
                </p>
              </div>
            ) : (
              <div className="flex-1 bg-slate-900/50 border border-slate-800 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center">
                <div className="p-4 bg-slate-800/80 rounded-full text-slate-500 mb-4">
                  <Server className="w-8 h-8" />
                </div>
                <h3 className="text-sm font-semibold text-slate-300 mb-1">
                  No Active Terminal
                </h3>
                <p className="text-xs text-slate-500 max-w-sm">
                  Click &ldquo;Request Linux Container&rdquo; on the left to spawn an isolated environment and run commands in your browser.
                </p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
export default App;
