import { useCallback, useEffect, useState } from 'react';
import StudentPortal from './StudentPortal';
import { AdminDashboard } from './components/AdminDashboard';

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
    if (response.status === 401 && url !== '/auth/login' && url !== '/auth/change-password') window.dispatchEvent(new Event('session-expired'));
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? undefined as T : response.json();
}

const inputStyle = 'w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white';
const buttonStyle = 'rounded bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-50';

function Accounts({ user }: { user: Identity }) {
  const [users, setUsers] = useState<User[]>([]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    try { setUsers(await request<User[]>('/admin/users')); }
    catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    try {
      await request('/admin/users', 'POST', { username, password }, user.csrf);
      setUsername(''); setPassword(''); setError(''); await refresh();
    } catch (e) { setError((e as Error).message); }
  }
  async function toggle(account: User) {
    try {
      await request(`/admin/users/${encodeURIComponent(account.id)}`, 'PATCH', { is_active: !account.is_active }, user.csrf);
      setError(''); await refresh();
    } catch (e) { setError((e as Error).message); }
  }
  async function reset(account: User, nextPassword: string) {
    try {
      await request(`/admin/users/${encodeURIComponent(account.id)}/reset-password`, 'POST', { password: nextPassword }, user.csrf);
      setError('');
    } catch (e) { setError((e as Error).message); }
  }
  return <section className="space-y-6">
    <div><h2 className="text-2xl font-semibold">Users</h2><p className="mt-1 text-sm text-slate-400">Create and manage student accounts.</p></div>
    {error && <p role="alert" className="text-rose-300">{error}</p>}
    <form onSubmit={create} className="grid gap-4 rounded-lg border border-slate-700 bg-slate-900 p-5 sm:grid-cols-3 sm:items-end">
      <label className="text-sm">Username<input className={inputStyle} required maxLength={128} value={username} onChange={e => setUsername(e.target.value)} /></label>
      <label className="text-sm">Initial password<input className={inputStyle} type="password" required maxLength={1024} value={password} onChange={e => setPassword(e.target.value)} /></label>
      <button className={buttonStyle}>Create student</button>
    </form>
    <div className="space-y-3">{users.map(account => <div key={account.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900 p-4">
      <div><p className="font-medium">{account.username}</p><p className="text-xs text-slate-400">{account.role} · {account.is_active ? 'Active' : 'Disabled'}</p></div>
      <div className="flex flex-wrap gap-2">
        {account.role === 'student' && <form onSubmit={event => { event.preventDefault(); const form = event.currentTarget; const value = new FormData(form).get('password'); if (typeof value === 'string' && value) { void reset(account, value); form.reset(); } }} className="flex gap-2">
          <input className={inputStyle} name="password" type="password" aria-label={`New password for ${account.username}`} placeholder="New password" required />
          <button className={buttonStyle}>Reset password</button>
        </form>}
        {account.id !== user.id && <button className="rounded border border-slate-600 px-3 py-2 text-sm" onClick={() => void toggle(account)}>{account.is_active ? 'Deactivate' : 'Activate'}</button>}
      </div>
    </div>)}</div>
  </section>;
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
    } catch (e) { setError((e as Error).message); }
  }
  return <section className="max-w-lg"><h2 className="mb-4 text-2xl font-semibold">Account settings</h2>
    <form onSubmit={submit} className="space-y-4 rounded-lg border border-slate-700 bg-slate-900 p-5">
      {error && <p role="alert" className="text-rose-300">{error}</p>}
      <label className="block text-sm">Current password<input className={inputStyle} type="password" autoComplete="current-password" required value={oldPassword} onChange={e => setOldPassword(e.target.value)} /></label>
      <label className="block text-sm">New password<input className={inputStyle} type="password" autoComplete="new-password" required value={newPassword} onChange={e => setNewPassword(e.target.value)} /></label>
      <button className={buttonStyle}>Change password</button>
    </form>
  </section>;
}

function SystemSettings() {
  const [settings, setSettings] = useState<Record<string, string | number> | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    request<Record<string, string | number>>('/settings').then(setSettings).catch(e => setError((e as Error).message));
  }, []);
  return <section><h2 className="text-2xl font-semibold">System settings</h2>
    <p className="my-3 text-sm text-slate-400">These settings are read from the backend configuration. Changes require an operator to restart the service.</p>
    {error && <p role="alert" className="text-rose-300">{error}</p>}
    {!settings && !error && <p>Loading settings…</p>}
    {settings && <dl className="max-w-2xl divide-y divide-slate-700 rounded-lg border border-slate-700 bg-slate-900 px-4">
      {Object.entries(settings).map(([key, value]) => <div key={key} className="flex justify-between gap-4 py-3 text-sm"><dt>{key.replaceAll('_', ' ')}</dt><dd className="text-slate-300">{value}</dd></div>)}
    </dl>}
  </section>;
}

export default function App() {
  const [user, setUser] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [section, setSection] = useState('overview');

  const signOut = useCallback(() => {
    setUser(null); setPassword(''); setSection('overview');
    window.history.replaceState(null, '', '/login');
  }, []);
  useEffect(() => {
    const expired = () => signOut();
    window.addEventListener('session-expired', expired);
    request<Identity>('/auth/me').then(identity => {
      setUser(identity);
      const target = identity.role === 'admin' ? '/admin' : '/student';
      if (window.location.pathname !== target) window.history.replaceState(null, '', target);
    }).catch(() => signOut()).finally(() => setLoading(false));
    return () => window.removeEventListener('session-expired', expired);
  }, [signOut]);

  async function login(event: React.FormEvent) {
    event.preventDefault(); setError(''); setLoading(true);
    try {
      await request('/auth/login', 'POST', { username, password });
      const identity = await request<Identity>('/auth/me');
      setPassword(''); setUser(identity);
      window.history.replaceState(null, '', identity.role === 'admin' ? '/admin' : '/student');
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }
  async function logout() {
    if (!user) return;
    try { await request('/auth/logout', 'POST', undefined, user.csrf); signOut(); }
    catch (e) { setError((e as Error).message); }
  }
  if (loading && !user) return <div className="min-h-screen bg-slate-950 p-8 text-slate-200">Loading…</div>;
  if (!user) return <main className="flex min-h-screen items-center justify-center bg-slate-950 p-4 text-slate-100">
    <form onSubmit={login} className="w-full max-w-sm space-y-5 rounded-xl border border-slate-700 bg-slate-900 p-8">
      <div><h1 className="text-2xl font-semibold">OpenLabScale</h1><p className="mt-1 text-sm text-slate-400">Sign in to your workspace</p></div>
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      <label className="block text-sm">Username<input className={inputStyle} autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} /></label>
      <label className="block text-sm">Password<input className={inputStyle} type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
      <button className={buttonStyle} disabled={loading}>Sign in</button>
    </form>
  </main>;

  return <div className="min-h-screen bg-slate-950 text-slate-100">
    <header className="border-b border-slate-800 bg-slate-900 px-5 py-4">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
        <div><h1 className="font-semibold">OpenLabScale {user.role === 'admin' ? 'Admin' : 'Student'}</h1><p className="text-xs text-slate-400">Signed in as {user.username}</p></div>
        <nav aria-label="Portal navigation" className="flex flex-wrap items-center gap-3 text-sm">
          <button onClick={() => setSection('overview')}>{user.role === 'admin' ? 'Overview' : 'My workspaces'}</button>
          {user.role === 'admin' && <button onClick={() => setSection('users')}>Users</button>}
          {user.role === 'admin' && <button onClick={() => setSection('settings')}>System settings</button>}
          <button onClick={() => setSection('account')}>Account settings</button>
          <button onClick={() => void logout()}>Sign out</button>
        </nav>
      </div>
    </header>
    {error && <p role="alert" className="mx-auto max-w-7xl p-4 text-rose-300">{error}</p>}
    {section === 'account' ? <main className="mx-auto max-w-7xl p-6"><AccountSettings user={user} onSignOut={signOut} /></main>
      : section === 'users' && user.role === 'admin' ? <main className="mx-auto max-w-7xl p-6"><Accounts user={user} /></main>
      : section === 'settings' && user.role === 'admin' ? <main className="mx-auto max-w-7xl p-6"><SystemSettings /></main>
      : user.role === 'admin' ? <main className="mx-auto max-w-7xl p-6"><AdminDashboard token={user.csrf} identityLabel={user.username} /></main>
      : <StudentPortal csrf={user.csrf} />}
  </div>;
}
