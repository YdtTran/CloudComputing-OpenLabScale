"""HTTP server and state management for OpenLab-Scale Dashboard."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

STATIC_DIR = Path(__file__).resolve().parent / 'static'
TOTAL_LICENSE_SEATS = 5


class DashboardState:
    """Thread-safe state management for containers, telemetry, and floating licenses."""
    def __init__(self, total_seats=TOTAL_LICENSE_SEATS):
        self.lock = threading.Lock()
        self.total_seats = total_seats
        self.sessions = {}
        self.audit_log = []
        self._init_defaults()

    def _init_defaults(self):
        # Seed realistic initial lab workspaces
        now = time.time()
        self.sessions = {
            "sess-matlab-01": {
                "session_id": "sess-matlab-01",
                "user": "Nguyen Van A (2414001)",
                "tool": "MATLAB R2024b",
                "container_id": "c71a8f921d",
                "cpu_pct": 0.05,
                "memory_mb": 184.2,
                "ebpf_exec_count": 0,
                "idle_seconds": 45,
                "status": "IDLE_CANDIDATE",
                "telemetry_status": "OK",
                "acquired_at": now - 3600,
                "seat_id": 1,
            },
            "sess-cadence-02": {
                "session_id": "sess-cadence-02",
                "user": "Tran Thi B (2413603)",
                "tool": "Cadence Virtuoso",
                "container_id": "e44b912c0a",
                "cpu_pct": 38.4,
                "memory_mb": 242.0,
                "ebpf_exec_count": 14,
                "idle_seconds": 0,
                "status": "ACTIVE",
                "telemetry_status": "OK",
                "acquired_at": now - 1800,
                "seat_id": 2,
            },
            "sess-ansys-03": {
                "session_id": "sess-ansys-03",
                "user": "Le Van C (2414100)",
                "tool": "Ansys HFSS",
                "container_id": "a183ff402b",
                "cpu_pct": 0.0,
                "memory_mb": 110.5,
                "ebpf_exec_count": 0,
                "idle_seconds": 12,
                "status": "IDLE",
                "telemetry_status": "OK",
                "acquired_at": now - 900,
                "seat_id": 3,
            },
        }
        self.record_audit("SYSTEM_INIT", "License pool initialized with 5 seats; 3 sessions loaded.")

    def record_audit(self, action, message, session_id=None):
        entry = {
            "timestamp": time.strftime("%H:%M:%S"),
            "action": action,
            "message": message,
            "session_id": session_id,
        }
        self.audit_log.insert(0, entry)
        if len(self.audit_log) > 50:
            self.audit_log.pop()

    def get_status(self):
        with self.lock:
            active_leases = [s for s in self.sessions.values() if s.get("seat_id")]
            in_use = len(active_leases)
            return {
                "license_pool": {
                    "total_seats": self.total_seats,
                    "in_use": in_use,
                    "free_seats": max(0, self.total_seats - in_use),
                    "utilization_pct": round((in_use / self.total_seats) * 100, 1),
                },
                "sessions": list(self.sessions.values()),
                "audit_log": list(self.audit_log[:15]),
            }

    def checkout_license(self, session_id, user, tool="MATLAB"):
        with self.lock:
            if session_id in self.sessions and self.sessions[session_id].get("seat_id"):
                return False, "Session already holds an active license seat"

            active_seats = {s["seat_id"] for s in self.sessions.values() if s.get("seat_id")}
            available_seats = [i for i in range(1, self.total_seats + 1) if i not in active_seats]
            if not available_seats:
                self.record_audit("CHECKOUT_DENIED", f"License pool exhausted ({self.total_seats}/{self.total_seats} in use). Request rejected for {user}.")
                return False, "LICENSE_POOL_EXHAUSTED"

            seat_id = available_seats[0]
            cid = os.urandom(5).hex()
            self.sessions[session_id] = {
                "session_id": session_id,
                "user": user,
                "tool": tool,
                "container_id": cid,
                "cpu_pct": 12.5,
                "memory_mb": 95.0,
                "ebpf_exec_count": 3,
                "idle_seconds": 0,
                "status": "ACTIVE",
                "telemetry_status": "OK",
                "acquired_at": time.time(),
                "seat_id": seat_id,
            }
            self.record_audit("CHECKOUT_SUCCESS", f"Seat #{seat_id} checked out for {user} ({tool}).", session_id)
            return True, {"seat_id": seat_id, "session_id": session_id}

    def release_license(self, session_id):
        with self.lock:
            if session_id not in self.sessions:
                return False, "Session not found"
            session = self.sessions.pop(session_id)
            seat_id = session.get("seat_id")
            self.record_audit("RELEASE_VOLUNTARY", f"User {session['user']} released Seat #{seat_id}.", session_id)
            return True, {"released_seat": seat_id}

    def simulate_telemetry_event(self, session_id, event_type):
        """Simulate workload fluctuations or idle transitions for demo purposes."""
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return False, "Session not found"

            if event_type == "burst":
                session["cpu_pct"] = 42.0
                session["ebpf_exec_count"] += 5
                session["idle_seconds"] = 0
                session["status"] = "ACTIVE"
                self.record_audit("TELEMETRY_BURST", f"eBPF captured 5 exec calls & CPU burst for {session['user']}.", session_id)
            elif event_type == "idle_gap":
                session["cpu_pct"] = 0.02
                session["ebpf_exec_count"] = 0
                session["idle_seconds"] = 40
                session["status"] = "IDLE_CANDIDATE"
                self.record_audit("POLICY_CANDIDATE", f"Continuous quiet time >= 30s. Proposed IDLE_CANDIDATE for {session['user']}.", session_id)
            elif event_type == "degrade":
                session["telemetry_status"] = "DEGRADED"
                session["status"] = "UNKNOWN"
                self.record_audit("FAIL_SAFE_ALERT", f"Missing signal detected. Session {session_id} locked to UNKNOWN (reclaim disabled).", session_id)
            return True, session

    def approve_reclaim(self, session_id):
        """Human-in-the-loop admin approval with safety fencing verification."""
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return False, "Session not found"

            # Invariant 4: No unapproved or degraded reclaim
            if session["telemetry_status"] == "DEGRADED" or session["status"] == "UNKNOWN":
                return False, "SAFETY_VIOLATION: Cannot reclaim container under DEGRADED or UNKNOWN telemetry."

            if session["status"] != "IDLE_CANDIDATE":
                return False, f"SAFETY_VIOLATION: Session is {session['status']}, not IDLE_CANDIDATE."

            # Fencing check & Stop execution
            seat_id = session.get("seat_id")
            user = session["user"]
            tool = session["tool"]
            cid = session["container_id"]

            # Try docker inspect if running as real container
            try:
                res = subprocess.run(["docker", "inspect", cid], capture_output=True, text=True, timeout=1)
                if res.returncode == 0:
                    subprocess.run(["docker", "stop", cid], capture_output=True, timeout=5)
            except Exception:
                pass  # Mock container or container already terminated

            # Revoke lease & release seat
            del self.sessions[session_id]
            self.record_audit(
                "ADMIN_RECLAIM_APPROVED",
                f"Admin approved reclaim for {user} ({tool}). Container {cid} stopped. Seat #{seat_id} returned to pool.",
                session_id
            )
            return True, {
                "reclaimed_session": session_id,
                "returned_seat": seat_id,
                "reclaimed_user": user,
            }


class DashboardHandler(BaseHTTPRequestHandler):
    state = DashboardState()

    def _json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/status':
            self._json(200, self.state.get_status())
        elif parsed.path == '/api/audit':
            self._json(200, self.state.audit_log)
        else:
            # Serve index.html
            index_path = STATIC_DIR / 'index.html'
            if index_path.exists():
                content = index_path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Static index.html not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}

        if parsed.path == '/api/license/checkout':
            user = body.get('user', 'Student User')
            tool = body.get('tool', 'MATLAB')
            session_id = body.get('session_id', f'sess-{os.urandom(3).hex()}')
            ok, res = self.state.checkout_license(session_id, user, tool)
            self._json(200 if ok else 400, {"success": ok, "result": res})

        elif parsed.path == '/api/license/release':
            session_id = body.get('session_id')
            ok, res = self.state.release_license(session_id)
            self._json(200 if ok else 400, {"success": ok, "result": res})

        elif parsed.path == '/api/reclaim/approve':
            session_id = body.get('session_id')
            ok, res = self.state.approve_reclaim(session_id)
            self._json(200 if ok else 400, {"success": ok, "result": res})

        elif parsed.path == '/api/simulate/event':
            session_id = body.get('session_id')
            event_type = body.get('event_type')
            ok, res = self.state.simulate_telemetry_event(session_id, event_type)
            self._json(200 if ok else 400, {"success": ok, "result": res})

        else:
            self.send_error(404, "API route not found")


def run_server(port=8500):
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, DashboardHandler)
    print(f"OpenLab-Scale Dashboard running at http://localhost:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server...")
        httpd.server_close()
