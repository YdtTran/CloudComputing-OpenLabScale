import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  Bell,
  Cpu,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Play,
  Search,
  Settings,
  Shield,
  Terminal,
  User as UserIcon,
  Users,
  X,
} from 'lucide-react';
import StudentPortal from './StudentPortal';
import { AdminDashboard, type AdminAlert, type AdminView } from './components/AdminDashboard';

interface Identity {
  id: string;
  username: string;
  role: 'student' | 'admin';
  csrf: string;
}

interface User {
  id: string;
  username: string;
  role: 'student' | 'admin';
  is_active: boolean;
}

async function request<T>(url: string, method = 'GET', body?: object, csrf?: string): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    if (response.status === 401 && url !== '/auth/login' && url !== '/auth/change-password') {
      window.dispatchEvent(new Event('session-expired'));
    }
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

const inputStyle =
  'w-full rounded-md border border-white/10 bg-[#1e1e2f] px-3 py-2 text-sm text-white placeholder-[#9a9a9a] focus:outline-none focus:border-[#1d8cf8]';
const primaryBtn =
  'rounded-md bg-gradient-to-r from-[#1d8cf8] to-[#3358f4] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 cursor-pointer transition';

function Accounts({ user }: { user: Identity }) {
  const [users, setUsers] = useState<User[]>([]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    try {
      setUsers(await request<User[]>('/admin/users'));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    try {
      await request('/admin/users', 'POST', { username, password }, user.csrf);
      setUsername('');
      setPassword('');
      setError('');
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function toggle(account: User) {
    try {
      await request(
        `/admin/users/${encodeURIComponent(account.id)}`,
        'PATCH',
        { is_active: !account.is_active },
        user.csrf,
      );
      setError('');
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function reset(account: User, nextPassword: string) {
    try {
      await request(
        `/admin/users/${encodeURIComponent(account.id)}/reset-password`,
        'POST',
        { password: nextPassword },
        user.csrf,
      );
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="space-y-6">
      <div className="bg-[#27293d] rounded-lg p-6 shadow-lg border border-white/5">
        <p className="text-[11px] uppercase tracking-wider text-[#9a9a9a]">Identity Directory</p>
        <h2 className="text-2xl font-light text-white mt-0.5 mb-4">Users ({users.length})</h2>
        {error && (
          <p role="alert" className="text-sm text-[#fd5d93] mb-3">
            {error}
          </p>
        )}
        <form onSubmit={create} className="grid gap-4 rounded-lg border border-white/5 bg-[#1e1e2f] p-5 sm:grid-cols-3 sm:items-end">
          <label className="text-xs text-[#9a9a9a]">
            Username
            <input className={`${inputStyle} mt-1`} required maxLength={128} value={username} onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label className="text-xs text-[#9a9a9a]">
            Initial password
            <input className={`${inputStyle} mt-1`} type="password" required maxLength={1024} value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button className={primaryBtn}>Create student</button>
        </form>
      </div>
      <div className="bg-[#27293d] rounded-lg p-5 shadow-lg border border-white/5 divide-y divide-gray-700/50">
        {users.map((account) => (
          <div key={account.id} className="flex flex-wrap items-center justify-between gap-3 py-3.5">
            <div>
              <p className="font-medium text-white text-sm">{account.username}</p>
              <p className="text-xs text-[#9a9a9a]">
                {account.role} &middot; {account.is_active ? 'Active' : 'Disabled'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {account.role === 'student' && (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    const form = event.currentTarget;
                    const value = new FormData(form).get('password');
                    if (typeof value === 'string' && value) {
                      void reset(account, value);
                      form.reset();
                    }
                  }}
                  className="flex gap-2"
                >
                  <input
                    className={inputStyle}
                    name="password"
                    type="password"
                    aria-label={`New password for ${account.username}`}
                    placeholder="New password"
                    required
                  />
                  <button className={primaryBtn}>Reset password</button>
                </form>
              )}
              {account.id !== user.id && (
                <button
                  className="rounded-md border border-white/15 bg-[#1e1e2f] px-3 py-2 text-xs text-white hover:border-[#fd5d93] cursor-pointer"
                  onClick={() => void toggle(account)}
                >
                  {account.is_active ? 'Deactivate' : 'Activate'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function AccountSettings({ user, onSignOut }: { user: Identity; onSignOut: () => void }) {
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState('');
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await request('/auth/change-password', 'POST', { old_password: oldPassword, new_password: newPassword }, user.csrf);
      onSignOut();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="max-w-xl bg-[#27293d] rounded-lg p-6 shadow-lg border border-white/5 space-y-5">
      <div>
        <p className="text-[11px] uppercase tracking-wider text-[#9a9a9a]">Account Security</p>
        <h2 className="text-2xl font-light text-white mt-0.5">User Profile</h2>
      </div>
      <div className="grid grid-cols-2 gap-4 text-xs bg-[#1e1e2f] p-4 rounded-lg border border-white/5">
        <div>
          <span className="text-[#9a9a9a]">Username</span>
          <p className="text-white font-semibold mt-0.5">{user.username}</p>
        </div>
        <div>
          <span className="text-[#9a9a9a]">Role</span>
          <p className="text-[#00f2c3] font-semibold uppercase mt-0.5">{user.role}</p>
        </div>
      </div>
      <form onSubmit={submit} className="space-y-4">
        {error && (
          <p role="alert" className="text-sm text-[#fd5d93]">
            {error}
          </p>
        )}
        <label className="block text-xs text-[#9a9a9a]">
          Current password
          <input className={`${inputStyle} mt-1`} type="password" autoComplete="current-password" required value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} />
        </label>
        <label className="block text-xs text-[#9a9a9a]">
          New password
          <input className={`${inputStyle} mt-1`} type="password" autoComplete="new-password" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        </label>
        <button className={primaryBtn}>Change password</button>
      </form>
    </section>
  );
}

function SystemSettings() {
  const [settings, setSettings] = useState<Record<string, string | number | boolean> | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    request<Record<string, string | number | boolean>>('/settings').then(setSettings).catch((e) => setError((e as Error).message));
  }, []);
  return (
    <section className="bg-[#27293d] rounded-lg p-6 shadow-lg border border-white/5 space-y-4">
      <div>
        <p className="text-[11px] uppercase tracking-wider text-[#9a9a9a]">Runtime Configuration</p>
        <h2 className="text-2xl font-light text-white mt-0.5">System Settings</h2>
      </div>
      <p className="text-xs text-[#9a9a9a]">
        Read-only view of effective backend and eBPF thresholds. Updating configuration requires restarting Uvicorn.
      </p>
      {error && (
        <p role="alert" className="text-sm text-[#fd5d93]">
          {error}
        </p>
      )}
      {!settings && !error && <p className="text-xs text-[#9a9a9a]">Loading settings…</p>}
      {settings && (
        <dl className="divide-y divide-gray-700/50 rounded-lg border border-white/5 bg-[#1e1e2f] px-4">
          {Object.entries(settings).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-4 py-3 text-xs">
              <dt className="text-[#9a9a9a] uppercase tracking-wider">{key.replaceAll('_', ' ')}</dt>
              <dd className="font-mono text-white">{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

export default function App() {
  const [user, setUser] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [section, setSection] = useState<'dashboard' | 'demo' | 'tables' | 'notifications' | 'probes' | 'users' | 'settings' | 'account'>('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [notifOpen, setNotifOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [alerts, setAlerts] = useState<AdminAlert[]>([]);

  const signOut = useCallback(() => {
    setUser(null);
    setPassword('');
    setSection('dashboard');
    window.history.replaceState(null, '', '/login');
  }, []);

  useEffect(() => {
    const expired = () => signOut();
    window.addEventListener('session-expired', expired);
    request<Identity>('/auth/me')
      .then((identity) => {
        setUser(identity);
        const target = identity.role === 'admin' ? '/admin' : '/student';
        if (window.location.pathname !== target) window.history.replaceState(null, '', target);
      })
      .catch(() => signOut())
      .finally(() => setLoading(false));
    return () => window.removeEventListener('session-expired', expired);
  }, [signOut]);

  async function login(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      await request('/auth/login', 'POST', { username, password });
      const identity = await request<Identity>('/auth/me');
      setPassword('');
      setUser(identity);
      window.history.replaceState(null, '', identity.role === 'admin' ? '/admin' : '/student');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    if (!user || signingOut) return;
    setSigningOut(true);
    setNotifOpen(false);
    setProfileOpen(false);
    await new Promise((resolve) => setTimeout(resolve, 30));
    try {
      await request('/auth/logout', 'POST', undefined, user.csrf);
    } catch {
      // Session already expired or invalidated; clear local view cleanly.
    } finally {
      signOut();
      setSigningOut(false);
    }
  }

  if (loading && !user) {
    return <div className="min-h-screen bg-[#1e1e2f] p-8 text-white">Loading…</div>;
  }

  if (!user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#1e1e2f] p-4 text-white">
        <form onSubmit={login} className="w-full max-w-sm space-y-5 rounded-lg border border-white/10 bg-[#27293d] p-8 shadow-2xl">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#1d8cf8] to-[#3358f4] flex items-center justify-center">
              <Cpu className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-wide">OpenLabScale</h1>
              <p className="text-xs text-[#9a9a9a]">Sign in to your workspace</p>
            </div>
          </div>
          {error && (
            <p role="alert" className="text-sm text-[#fd5d93]">
              {error}
            </p>
          )}
          <label className="block text-xs text-[#9a9a9a]">
            Username
            <input className={`${inputStyle} mt-1`} autoComplete="username" required value={username} onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label className="block text-xs text-[#9a9a9a]">
            Password
            <input className={`${inputStyle} mt-1`} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button className={`w-full ${primaryBtn}`} disabled={loading}>
            Sign in
          </button>
        </form>
      </main>
    );
  }

  const adminNav: Array<{ id: typeof section; label: string; icon: typeof LayoutDashboard }> = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'demo', label: 'Demo Scenarios', icon: Play },
    { id: 'tables', label: 'Table List', icon: ListChecks },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'probes', label: 'Signals & Probes', icon: Cpu },
    { id: 'users', label: 'Users', icon: Users },
    { id: 'settings', label: 'System Settings', icon: Settings },
    { id: 'account', label: 'User Profile', icon: UserIcon },
  ];

  const studentNav: Array<{ id: typeof section; label: string; icon: typeof LayoutDashboard }> = [
    { id: 'dashboard', label: 'My Workspaces', icon: Terminal },
    { id: 'account', label: 'User Profile', icon: UserIcon },
  ];

  const navItems = user.role === 'admin' ? adminNav : studentNav;
  const pageTitle = navItems.find((n) => n.id === section)?.label.toUpperCase() ?? 'DASHBOARD';
  const adminDashboardView: AdminView =
    section === 'demo' || section === 'tables' || section === 'notifications' || section === 'probes'
      ? section
      : 'dashboard';
  const showAdminDashboard = user.role === 'admin' && section !== 'users' && section !== 'settings' && section !== 'account';

  return (
    <div className="min-h-screen bg-[#1e1e2f] text-white flex">
      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Electric Blue Gradient Left Sidebar */}
      <aside
        className={`fixed lg:sticky top-0 left-0 z-40 h-screen w-64 shrink-0 bg-gradient-to-b from-[#1d8cf8] to-[#3358f4] text-white shadow-2xl flex flex-col transition-transform duration-200 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <div className="px-6 py-5 flex items-center justify-between border-b border-white/20">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-white/15 flex items-center justify-center">
              <Activity className="w-4 h-4 text-white" />
            </div>
            <span className="text-sm font-semibold tracking-wider uppercase">OPENLABSCALE</span>
          </div>
          <button type="button" className="lg:hidden text-white/80 hover:text-white cursor-pointer" onClick={() => setSidebarOpen(false)}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav aria-label="Portal navigation" className="flex-1 px-4 py-5 space-y-1.5 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = section === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setSection(item.id);
                  setSidebarOpen(false);
                }}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs uppercase tracking-wider font-medium transition cursor-pointer ${
                  active ? 'bg-white/20 text-white shadow-sm' : 'text-white/80 hover:bg-white/10 hover:text-white'
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="p-4 border-t border-white/20 text-[11px] text-white/80 flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5" /> {user.role.toUpperCase()}
          </span>
          <button type="button" onClick={() => void logout()} className="flex items-center gap-1 hover:text-white cursor-pointer">
            <LogOut className="w-3.5 h-3.5" /> Sign out
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Minimalist Dark Top Navbar */}
        <header className="h-16 px-6 flex items-center justify-between border-b border-white/5 bg-[#1e1e2f] sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <button type="button" className="lg:hidden p-1.5 rounded bg-[#27293d] text-white cursor-pointer" onClick={() => setSidebarOpen(true)}>
              <Menu className="w-5 h-5" />
            </button>
            <span className="text-sm font-medium tracking-widest text-white uppercase">{pageTitle}</span>
          </div>

          <div className="flex items-center gap-4 relative">
            {user.role === 'admin' && (
              <>
                <button
                  type="button"
                  aria-label="Search sessions"
                  onClick={() => setSearchOpen(true)}
                  className="p-2 rounded-full text-slate-300 hover:text-white hover:bg-[#27293d] transition cursor-pointer"
                >
                  <Search className="w-4 h-4" />
                </button>

                <div className="relative">
                  <button
                    type="button"
                    aria-label="Notifications"
                    onClick={() => {
                      setNotifOpen((p) => !p);
                      setProfileOpen(false);
                    }}
                    className="p-2 rounded-full text-slate-300 hover:text-white hover:bg-[#27293d] transition cursor-pointer relative"
                  >
                    <Bell className="w-4 h-4" />
                    {alerts.length > 0 && (
                      <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#fd5d93] animate-pulse" />
                    )}
                  </button>
                  {notifOpen && (
                    <div className="absolute right-0 mt-2 w-80 rounded-lg bg-[#27293d] border border-white/10 shadow-2xl p-3 space-y-2 z-50 text-xs">
                      <div className="flex justify-between items-center pb-2 border-b border-white/10">
                        <span className="font-semibold text-white">Live Alerts ({alerts.length})</span>
                        <button
                          type="button"
                          onClick={() => {
                            setNotifOpen(false);
                            setSection('notifications');
                          }}
                          className="text-[#1d8cf8] hover:underline cursor-pointer"
                        >
                          View all
                        </button>
                      </div>
                      {alerts.length === 0 ? (
                        <p className="text-[#9a9a9a] py-2">No active alerts.</p>
                      ) : (
                        alerts.slice(0, 4).map((a) => (
                          <div key={a.id} className="p-2 rounded bg-[#1e1e2f]">
                            <div className="font-semibold text-white">{a.title}</div>
                            <div className="text-[#9a9a9a] text-[11px] truncate">{a.detail}</div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </>
            )}

            <div className="relative">
              <button
                type="button"
                aria-label="Profile menu"
                onClick={() => {
                  setProfileOpen((p) => !p);
                  setNotifOpen(false);
                }}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-full bg-[#27293d] border border-white/10 hover:border-[#1d8cf8] transition cursor-pointer text-xs"
              >
                <div className="w-6 h-6 rounded-full bg-gradient-to-br from-[#1d8cf8] to-[#e14eca] flex items-center justify-center font-bold text-[11px]">
                  {user.username.slice(0, 1).toUpperCase()}
                </div>
                <span className="hidden sm:inline text-white font-medium">{user.username}</span>
              </button>
              {profileOpen && (
                <div className="absolute right-0 mt-2 w-48 rounded-lg bg-[#27293d] border border-white/10 shadow-2xl py-2 z-50 text-xs">
                  <button
                    type="button"
                    onClick={() => {
                      setProfileOpen(false);
                      setSection('account');
                    }}
                    className="w-full px-4 py-2 text-left text-slate-200 hover:bg-white/5 cursor-pointer"
                  >
                    User Profile
                  </button>
                  {user.role === 'admin' && (
                    <button
                      type="button"
                      onClick={() => {
                        setProfileOpen(false);
                        setSection('settings');
                      }}
                      className="w-full px-4 py-2 text-left text-slate-200 hover:bg-white/5 cursor-pointer"
                    >
                      System Settings
                    </button>
                  )}
                  <div className="my-1 border-t border-white/10" />
                  <button
                    type="button"
                    onClick={() => {
                      setProfileOpen(false);
                      void logout();
                    }}
                    className="w-full px-4 py-2 text-left text-[#fd5d93] hover:bg-white/5 cursor-pointer"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {error && (
          <p role="alert" className="mx-6 mt-4 p-3 rounded bg-[#fd5d93]/15 border border-[#fd5d93]/40 text-xs text-[#fd5d93]">
            {error}
          </p>
        )}

        <main className="flex-1 p-6 max-w-[1600px] w-full mx-auto">
          {section === 'account' ? (
            <AccountSettings user={user} onSignOut={signOut} />
          ) : section === 'users' && user.role === 'admin' ? (
            <Accounts user={user} />
          ) : section === 'settings' && user.role === 'admin' ? (
            <SystemSettings />
          ) : showAdminDashboard ? (
            <AdminDashboard
              token={user.csrf}
              identityLabel={user.username}
              activeView={adminDashboardView}
              onNavigate={(v) => setSection(v)}
              onStatsSync={(_, nextAlerts) => setAlerts(nextAlerts)}
              externalSearch={appliedSearch}
              signingOut={signingOut}
            />
          ) : (
            <StudentPortal csrf={user.csrf} signingOut={signingOut} />
          )}
        </main>
      </div>

      {/* Quick Search Modal */}
      {searchOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center pt-24 p-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setAppliedSearch(searchTerm);
              setSearchOpen(false);
              setSection('tables');
            }}
            className="w-full max-w-lg bg-[#27293d] rounded-lg border border-white/10 p-5 shadow-2xl space-y-4"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-[#9a9a9a]">Search Sessions / Students</span>
              <button type="button" onClick={() => setSearchOpen(false)} className="text-[#9a9a9a] hover:text-white cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
            <input
              autoFocus
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Type session ID, username, or container ID..."
              className={inputStyle}
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setSearchTerm('');
                  setAppliedSearch('');
                  setSearchOpen(false);
                }}
                className="px-3 py-1.5 rounded bg-[#1e1e2f] text-xs text-[#9a9a9a] cursor-pointer"
              >
                Clear
              </button>
              <button type="submit" className={primaryBtn}>
                Filter Table
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
