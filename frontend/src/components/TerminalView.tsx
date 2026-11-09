import React, { useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { AlertCircle, Terminal as TerminalIcon, RefreshCw } from 'lucide-react';

interface TerminalViewProps {
  sessionId: string;
  token: string;
}

export const TerminalView: React.FC<TerminalViewProps> = ({ sessionId, token }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState<boolean>(false);
  const [reconnectKey, setReconnectKey] = useState<number>(0);

  useEffect(() => {
    if (!containerRef.current) return;
    let isMounted = true;
    containerRef.current.innerHTML = '';

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: 'block',
      fontFamily: 'Consolas, "Courier New", monospace, ui-monospace',
      fontSize: 14,
      lineHeight: 1.25,
      convertEol: true,
      theme: {
        background: '#090d16',
        foreground: '#e2e8f0',
        cursor: '#38bdf8',
        selectionBackground: '#1e293b',
      },
    });
    termRef.current = term;

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(containerRef.current);

    const fitTimer = setTimeout(() => {
      try {
        fitAddon.fit();
      } catch {
        // ignore layout race
      }
    }, 50);

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/sessions/${encodeURIComponent(sessionId)}/terminal`;
    const ws = new WebSocket(wsUrl, ['openlabscale', `auth.${token}`]);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      if (!isMounted) return;
      setConnected(true);
      setError(null);
      const rows = Math.max(1, Math.min(500, term.rows || 24));
      const cols = Math.max(1, Math.min(500, term.cols || 80));
      ws.send(JSON.stringify({ rows, cols }));
      term.focus();
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!isMounted) return;
      if (event.data instanceof ArrayBuffer) {
        term.write(new Uint8Array(event.data));
      } else if (typeof event.data === 'string') {
        term.write(event.data);
      }
    };

    ws.onclose = (event: CloseEvent) => {
      if (!isMounted) return;
      setConnected(false);
      if (event.code === 1008) {
        setError('Access denied (not session owner, invalid token, session not running, or terminal already attached).');
      } else if (event.code !== 1000) {
        setError(`Connection closed (code: ${event.code}). Click Reconnect to retry.`);
      }
      term.writeln('\r\n\x1b[33m[Session disconnected]\x1b[0m');
    };

    const dataListener = term.onData((data: string) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(new TextEncoder().encode(data));
      }
    });

    const resizeListener = term.onResize(({ rows, cols }: { rows: number; cols: number }) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(
          JSON.stringify({
            rows: Math.max(1, Math.min(500, rows)),
            cols: Math.max(1, Math.min(500, cols)),
          }),
        );
      }
    });

    const handleResize = () => {
      try {
        fitAddon.fit();
      } catch {
        // ignore
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      isMounted = false;
      clearTimeout(fitTimer);
      window.removeEventListener('resize', handleResize);
      dataListener.dispose();
      resizeListener.dispose();
      ws.close();
      term.dispose();
      termRef.current = null;
    };
  }, [sessionId, token, reconnectKey]);

  return (
    <div className="flex flex-col h-full bg-slate-900 border border-slate-700 rounded-lg overflow-hidden shadow-xl">
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-800 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <TerminalIcon className="w-4 h-4 text-sky-400" />
          <span className="font-mono text-xs text-slate-300 font-semibold">
            session:{sessionId.slice(0, 8)} terminal
          </span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setReconnectKey((k) => k + 1)}
            className="flex items-center gap-1 text-[11px] px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded transition cursor-pointer"
            title="Reconnect terminal WebSocket"
          >
            <RefreshCw className="w-3 h-3" />
            Reconnect
          </button>
          <div className="flex items-center gap-2">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                connected ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'
              }`}
            />
            <span className="text-xs text-slate-400 font-mono">
              {connected ? 'Live Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      </div>

      {error && (
        <div className="flex items-center justify-between px-4 py-2 bg-amber-950/80 border-b border-amber-700/50 text-amber-200 text-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setReconnectKey((k) => k + 1)}
            className="text-xs font-semibold text-sky-400 hover:text-sky-300 underline ml-2 cursor-pointer"
          >
            Try Again
          </button>
        </div>
      )}

      <div
        className="relative flex-1 p-3 bg-[#090d16] min-h-[420px] cursor-text"
        onClick={() => termRef.current?.focus()}
      >
        <div ref={containerRef} className="w-full h-full min-h-[400px]" />
      </div>
    </div>
  );
};
