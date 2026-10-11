import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import {
  Activity, ArrowLeft, ArrowRight, CheckCircle2, ClipboardList, Clock3,
  Copy, Database, FileClock, HelpCircle, LockKeyhole, RefreshCw, Search,
  Server, ShieldCheck, ShieldAlert, Sprout, UserRound, Users, X,
} from 'lucide-react';
import { supabase } from './supabase';
import type { Language } from './i18n';
import { adminText } from './adminI18n';

// Only server-authorized aggregate information, registered names and moderation records.
// Never query auth.users, private analysis reports, email addresses or Storage from here.
const API_BASE = (import.meta.env.VITE_AI_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
type Tab = 'overview' | 'users' | 'cases' | 'audit';
type AccountStatus = 'active' | 'blocked' | 'banned';
type UserRow = { id: string; display_name: string; status: AccountStatus; expires_at: string | null };
type UsersPayload = { items: UserRow[]; total: number | null; page: number; page_size: number };
type Stats = {
  total_users: number;
  total_saved_analyses: number;
  healthy_analyses: number;
  diseased_analyses: number;
  review_analyses: number;
};
type System = { api: string; supabase_database: string; note?: string };
type IoT = { configured?: boolean; online?: boolean };
type Case = { id: string; user_id: string | null; reason: string; status: 'open' | 'reviewing' | 'resolved'; created_at: string; resolved_at: string | null };
type Audit = { id: string; admin_id: string | null; target_user_id: string; action: string; reason: string; created_at: string };
type ModerationAction = 'block_24h' | 'block_7d' | 'ban' | 'unblock';
type Message = { kind: 'success' | 'error'; text: string };

async function adminRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  if (!supabase) throw new Error('Authentication is not configured.');
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session?.access_token) throw new Error('Your session has expired. Please sign in again.');
  const headers = new Headers(options.headers);
  headers.set('Authorization', `Bearer ${data.session.access_token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
  } catch {
    throw new Error('Cannot reach the LeafLens backend. Check that Python is running.');
  }
  const dataJson: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = dataJson && typeof dataJson === 'object' && 'detail' in dataJson && typeof dataJson.detail === 'string'
      ? dataJson.detail : `Server returned HTTP ${response.status}.`;
    throw new Error(detail);
  }
  return dataJson as T;
}

function friendlyDate(iso: string | null | undefined, language: Language) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? d.toLocaleString(language === 'hi' ? 'hi-IN' : 'en-IN') : '—';
}
function shortId(id: string | null | undefined, language: Language) {
  return id ? `${id.slice(0, 8)}…${id.slice(-4)}` : adminText(language, 'Account removed');
}
function StatusTag({ status, language }: { status: string; language: Language }) {
  const kind = status === 'active' || status === 'online' || status === 'resolved' ? 'good'
    : status === 'blocked' || status === 'open' || status === 'reviewing' ? 'amber' : 'red';
  return <span className={`admin-tag admin-tag-${kind}`}>{adminText(language, status.replace(/_/g, ' '))}</span>;
}
function CopyAccount({ id, language }: { id: string; language: Language }) {
  const [copied, setCopied] = useState(false);
  return <button type="button" className="admin-copy" title={adminText(language, 'Copy account ID')} aria-label={adminText(language, 'Copy account ID')} onClick={() => {
    void navigator.clipboard.writeText(id).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1800); });
  }}>{copied ? <CheckCircle2 size={14} /> : <Copy size={14} />}</button>;
}

export function AdminDashboard({ onBack, ownUserId, language }: { onBack?: () => void; ownUserId: string; language: Language }) {
  const tr = (text: string) => adminText(language, text);
  const [tab, setTab] = useState<Tab>('overview');
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [message, setMessage] = useState<Message | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [system, setSystem] = useState<System | null>(null);
  const [iot, setIot] = useState<IoT | null>(null);
  const [users, setUsers] = useState<UsersPayload>({ items: [], total: null, page: 1, page_size: 25 });
  const [searchInput, setSearchInput] = useState('');
  const [query, setQuery] = useState('');
  const [usersPage, setUsersPage] = useState(1);
  const [selected, setSelected] = useState<UserRow | null>(null);
  const [action, setAction] = useState<ModerationAction>('block_24h');
  const [reason, setReason] = useState('');
  const [confirmedId, setConfirmedId] = useState('');
  const [actionBusy, setActionBusy] = useState(false);
  const [cases, setCases] = useState<Case[]>([]);
  const [casesPage, setCasesPage] = useState(1);
  const [caseUserId, setCaseUserId] = useState('');
  const [caseReason, setCaseReason] = useState('');
  const [caseBusy, setCaseBusy] = useState(false);
  const [audits, setAudits] = useState<Audit[]>([]);
  const [auditPage, setAuditPage] = useState(1);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setLoadError('');
    const load = async () => {
      try {
        if (tab === 'overview') {
          const [s, sys, localIoT] = await Promise.all([
            adminRequest<Stats>('/api/admin/stats'),
            adminRequest<System>('/api/admin/system'),
            fetch(`${API_BASE}/api/iot/current`).then(r => r.ok ? r.json() as Promise<IoT> : null).catch(() => null),
          ]);
          if (alive) { setStats(s); setSystem(sys); setIot(localIoT); }
        } else if (tab === 'users') {
          const result = await adminRequest<UsersPayload>(`/api/admin/users?search=${encodeURIComponent(query)}&page=${usersPage}`);
          if (alive) setUsers(result);
        } else if (tab === 'cases') {
          const result = await adminRequest<{ items: Case[] }>(`/api/admin/cases?page=${casesPage}`);
          if (alive) setCases(result.items || []);
        } else {
          const result = await adminRequest<{ items: Audit[] }>(`/api/admin/audit?page=${auditPage}`);
          if (alive) setAudits(result.items || []);
        }
      } catch (err: unknown) {
        if (alive) setLoadError(err instanceof Error ? err.message : 'Could not load admin data.');
      } finally {
        if (alive) setLoading(false);
      }
    };
    void load();
    return () => { alive = false; };
  }, [tab, refreshKey, usersPage, query, casesPage, auditPage]);

  function changeTab(next: Tab) { setTab(next); setMessage(null); }
  function selectUser(user: UserRow) {
    setSelected(user);
    setReason(''); setConfirmedId(''); setMessage(null);
    setAction(user.status === 'active' ? 'block_24h' : 'unblock');
  }
  async function moderate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || actionBusy || confirmedId.trim() !== selected.id || reason.trim().length < 8) return;
    const phrase = action === 'ban' ? 'permanently ban' : action === 'unblock' ? 'restore access for' : 'temporarily block';
    if (!window.confirm(language === 'hi'
      ? `पुष्टि करें: ${selected.display_name} (${shortId(selected.id, language)}) — ${action === 'ban' ? 'स्थायी प्रतिबंध' : action === 'unblock' ? 'पहुँच वापस देना' : 'अस्थायी ब्लॉक'}?`
      : `Confirm: ${phrase} ${selected.display_name} (${shortId(selected.id, language)})?`)) return;
    setActionBusy(true); setMessage(null);
    try {
      await adminRequest(`/api/admin/users/${encodeURIComponent(selected.id)}/moderate`, {
        method: 'POST', body: JSON.stringify({ action, reason: reason.trim(), confirm_account_id: selected.id }),
      });
      setMessage({ kind: 'success', text: 'Account moderation completed.' });
      setSelected(null); setReason(''); setConfirmedId(''); setRefreshKey(x => x + 1);
    } catch (err: unknown) {
      setMessage({ kind: 'error', text: err instanceof Error ? err.message : 'Could not perform moderation action.' });
    } finally { setActionBusy(false); }
  }
  async function createCase(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (caseBusy) return;
    setCaseBusy(true); setMessage(null);
    try {
      await adminRequest('/api/admin/cases', { method: 'POST', body: JSON.stringify({ account_id: caseUserId.trim(), reason: caseReason.trim() }) });
      setCaseUserId(''); setCaseReason(''); setCasesPage(1);
      setRefreshKey(x => x + 1);
      setMessage({ kind: 'success', text: 'Moderation case created. No user restriction has been applied.' });
    } catch (err: unknown) {
      setMessage({ kind: 'error', text: err instanceof Error ? err.message : 'Could not create moderation case.' });
    } finally { setCaseBusy(false); }
  }
  async function resolveCase(item: Case) {
    if (caseBusy || !window.confirm(language === 'hi' ? `मामला ${shortId(item.id, language)} सुलझाया हुआ चिह्नित करें?` : `Mark case ${shortId(item.id, language)} as resolved?`)) return;
    setCaseBusy(true); setMessage(null);
    try {
      await adminRequest(`/api/admin/cases/${encodeURIComponent(item.id)}/resolve`, { method: 'POST' });
      setMessage({ kind: 'success', text: 'Case marked as resolved.' });
      setRefreshKey(x => x + 1);
    } catch (err: unknown) {
      setMessage({ kind: 'error', text: err instanceof Error ? err.message : 'Could not resolve case.' });
    } finally { setCaseBusy(false); }
  }

  const statTiles = stats ? [
    { label: 'Registered Users', value: stats.total_users, icon: Users },
    { label: 'Saved Analyses', value: stats.total_saved_analyses, icon: ClipboardList },
    { label: 'Healthy Results', value: stats.healthy_analyses, icon: Sprout },
    { label: 'Diseased Results', value: stats.diseased_analyses, icon: Activity },
    { label: 'Needs Review', value: stats.review_analyses, icon: ShieldAlert },
  ] : [];
  const totalPages = users.total == null ? null : Math.max(1, Math.ceil(users.total / users.page_size));
  const canNextUsers = totalPages === null ? users.items.length === users.page_size : usersPage < totalPages;

  return <section className="admin-dashboard">
    <header className="admin-heading">
      <div>
        {onBack && <button type="button" className="admin-back" onClick={onBack}><ArrowLeft size={16} /> {tr("Back to LeafLens")}</button>}
        <span className="admin-eyebrow"><ShieldCheck size={15} /> {tr("PRIVATE ADMIN WORKSPACE")}</span>
        <h1>{tr('Admin Dashboard')}</h1>
        <p>{tr("Monitor the platform and manage accounts without accessing anyone's private analyses or images.")}</p>
      </div>
      <button type="button" className="secondary-action admin-refresh" onClick={() => setRefreshKey(k => k + 1)} disabled={loading}>
        <RefreshCw size={16} className={loading ? 'admin-spinning' : ''} /> {tr("Refresh")}
      </button>
    </header>
    <div className="admin-nav" role="tablist" aria-label={tr('Admin sections')}>
      {([
        ['overview', Activity, 'Overview'], ['users', Users, 'Users'],
        ['cases', ShieldAlert, 'Moderation Cases'], ['audit', FileClock, 'Action History'],
      ] as const).map(([value, Icon, label]) => <button key={value} type="button" role="tab" aria-selected={tab === value}
        className={`admin-nav-button ${tab === value ? 'active' : ''}`} onClick={() => changeTab(value)}><Icon size={17} /> {tr(label)}</button>)}
    </div>
    {message && <div className={`admin-alert admin-alert-${message.kind}`} role="status">{message.kind === 'success' ? <CheckCircle2 size={18} /> : <ShieldAlert size={18} />}{tr(message.text)}<button aria-label={tr("Dismiss message")} type="button" onClick={() => setMessage(null)}><X size={16} /></button></div>}
    {loadError && <div className="admin-alert admin-alert-error" role="alert"><ShieldAlert size={18} /><span>{tr(loadError)}</span><button type="button" className="admin-text-button" onClick={() => setRefreshKey(k => k + 1)}>{tr('Retry')}</button></div>}
    {loading && <div className="admin-loading"><span className="spinner mini" /> {tr("Loading admin data…")}</div>}

    {tab === 'overview' && <div className="admin-content">
      <div className="admin-overview-grid">
        {statTiles.map(({ label, value, icon: Icon }) => <div className="card admin-stat" key={label}><span className="admin-stat-icon"><Icon size={22} /></span><span>{tr(label)}</span><strong>{value.toLocaleString(language === 'hi' ? 'hi-IN' : 'en-IN')}</strong></div>)}
        {!stats && !loading && <div className="card admin-empty">{tr('No statistics available yet. Use Refresh to retry.')}</div>}
      </div>
      <div className="admin-info-grid">
        <div className="card admin-information-card">
          <h2><Server size={20} /> {tr("System Health")}</h2>
          <div className="admin-health-line"><span><Activity size={17} /> {tr("FastAPI Server")}</span><StatusTag status={system?.api || 'unknown'} language={language} /></div>
          <div className="admin-health-line"><span><Database size={17} /> {tr("Supabase Database")}</span><StatusTag status={system?.supabase_database || 'unknown'} language={language} /></div>
          <div className="admin-health-line"><span><Sprout size={17} /> {tr("DHT11 Sensor")}</span><StatusTag status={iot?.online ? 'online' : iot?.configured ? 'offline' : 'not configured'} language={language} /></div>
          <p className="admin-footnote">{tr('Sensor connectivity reflects the local backend. Weather details remain on the Weather page.')}</p>
        </div>
        <div className="card admin-information-card">
          <h2><LockKeyhole size={20} /> {tr("Privacy & Moderation")}</h2>
          <p>{tr('Admin access is restricted to user display names, account IDs, statuses, aggregate counts and moderation records.')}</p>
          <div className="admin-privacy-line"><ShieldCheck size={18} /> {tr("Individual history, emails and personal images are not shown.")}</div>
        </div>
      </div>
    </div>}

    {tab === 'users' && <div className="admin-content">
      <div className="card admin-users-card">
        <div className="admin-section-head"><div><h2>{tr('User Management')}</h2><p>{tr('Find accounts by registered display name or exact account ID.')}</p></div><span className="admin-small-label">{tr('25 per page')}</span></div>
        <form className="admin-search" onSubmit={e => { e.preventDefault(); setUsersPage(1); setQuery(searchInput.trim()); setSelected(null); setRefreshKey(x => x + 1); }}>
          <Search size={20} /> <input type="search" value={searchInput} maxLength={80} onChange={e => setSearchInput(e.target.value)} placeholder={tr('Search user name or full account ID')} aria-label={tr('Search registered users')} />
          <button type="submit" className="primary-action">{tr('Search')}</button>
          {query && <button type="button" className="secondary-action" onClick={() => { setSearchInput(''); setQuery(''); setUsersPage(1); setSelected(null); }}>{tr('Clear')}</button>}
        </form>
        <div className="admin-table-scroll">
          <table className="admin-table"><thead><tr><th>{tr('Registered name')}</th><th>{tr('Account ID')}</th><th>{tr('Status')}</th><th></th></tr></thead><tbody>
            {users.items.map(user => <tr key={user.id}>
              <td><div className="admin-user-name"><span className="admin-user-icon"><UserRound size={18} /></span><strong>{user.display_name}</strong>{user.id === ownUserId && <span className="admin-you">{tr('You')}</span>}</div></td>
              <td><div className="admin-id-cell"><span title={user.id}>{shortId(user.id, language)}</span><CopyAccount id={user.id} language={language} /></div></td>
              <td><StatusTag status={user.status} language={language} />{user.status === 'blocked' && <small className="admin-expiry">{tr("Until")} {friendlyDate(user.expires_at, language)}</small>}</td>
              <td><button type="button" className="secondary-action admin-manage-button" disabled={user.id === ownUserId} onClick={() => selectUser(user)}>{tr("Manage")} <ArrowRight size={15} /></button></td>
            </tr>)}
          </tbody></table>
          {!users.items.length && !loading && !loadError && <div className="admin-empty">{tr('No matching registered users.')}</div>}
        </div>
        <div className="admin-pagination"><span>{users.total !== null ? `${users.total.toLocaleString(language === "hi" ? "hi-IN" : "en-IN")} ${tr("matching account(s)")}` : `${users.items.length.toLocaleString(language === "hi" ? "hi-IN" : "en-IN")} ${tr("loaded")}`}</span><div>
          <button type="button" className="secondary-action" disabled={usersPage <= 1 || loading} onClick={() => { setUsersPage(p => p - 1); setSelected(null); }}><ArrowLeft size={15} /> {tr("Previous")}</button>
          <span>{tr("Page")} {usersPage}{totalPages !== null ? ` ${tr("of")} ${totalPages}` : ''}</span>
          <button type="button" className="secondary-action" disabled={!canNextUsers || loading} onClick={() => { setUsersPage(p => p + 1); setSelected(null); }}>{tr("Next")} <ArrowRight size={15} /></button>
        </div></div>
      </div>
      {selected && <div className="card admin-moderation-card" id="admin-manage">
        <div className="admin-section-head"><div><h2>{tr('Manage Account')}</h2><p>{selected.display_name} · <span className="admin-code">{selected.id}</span></p></div><button type="button" className="admin-close" onClick={() => setSelected(null)} aria-label={tr('Close moderation panel')}><X size={21} /></button></div>
        <div className="admin-moderation-context"><StatusTag status={selected.status} language={language} /><span>{tr('Same names can belong to different users. Confirm the full Account ID before applying changes.')}</span></div>
        <form onSubmit={e => void moderate(e)} className="admin-moderation-form">
          <label>{tr('Moderation action')}
            <select value={action} onChange={e => setAction(e.target.value as ModerationAction)}>
              <option value="block_24h">{tr('Temporary Block — 24 hours')}</option><option value="block_7d">{tr('Temporary Block — 7 days')}</option><option value="ban">{tr('Permanent Ban')}</option><option value="unblock">{tr('Unblock / Remove Ban')}</option>
            </select>
          </label>
          <label>{tr('Reason (required, 8–500 characters)')}
            <textarea required minLength={8} maxLength={500} rows={3} value={reason} onChange={e => setReason(e.target.value)} placeholder={tr('Describe the moderation reason or appeal decision…')} />
          </label>
          <label>{tr('Confirm exact Account ID')}
            <input required value={confirmedId} onChange={e => setConfirmedId(e.target.value)} placeholder={tr('Paste the full account ID shown above')} autoComplete="off" />
          </label>
          <div className="admin-moderation-actions"><button type="submit" className={action === 'unblock' ? 'primary-action' : 'danger-action'} disabled={actionBusy || reason.trim().length < 8 || confirmedId.trim() !== selected.id}>
            {tr(actionBusy ? 'Saving…' : action === 'ban' ? 'Confirm Permanent Ban' : action === 'unblock' ? 'Restore Account Access' : 'Apply Temporary Block')}
          </button><button type="button" className="secondary-action" disabled={actionBusy} onClick={() => { setCaseUserId(selected.id); changeTab('cases'); }}>{tr('Open Moderation Case')}</button></div>
        </form>
      </div>}
    </div>}

    {tab === 'cases' && <div className="admin-content">
      <div className="admin-two-column">
        <div className="card admin-information-card">
          <h2><ShieldAlert size={20} /> {tr("Create Moderation Case")}</h2>
          <p>{tr('Record a complaint or investigation without automatically blocking anyone.')}</p>
          <form className="admin-case-form" onSubmit={e => void createCase(e)}>
            <label>{tr('Full Account ID')}<input required value={caseUserId} onChange={e => setCaseUserId(e.target.value)} placeholder={tr('Copy from User Management')} /></label>
            <label>{tr('Case description')}<textarea required rows={5} minLength={8} maxLength={1000} value={caseReason} onChange={e => setCaseReason(e.target.value)} placeholder={tr('Describe the complaint or reason for review…')} /></label>
            <button type="submit" className="primary-action" disabled={caseBusy || caseReason.trim().length < 8}>{tr(caseBusy ? 'Working…' : 'Create Case')}</button>
          </form>
        </div>
        <div className="card admin-information-card admin-case-list">
          <h2><ClipboardList size={20} /> {tr("Moderation Cases")}</h2>
          <p>{tr('Cases are manually created; there is no automatic complaint detection.')}</p>
          {cases.map(item => <article className="admin-case-item" key={item.id}>
            <div className="admin-case-top"><strong>{tr("Case")} {shortId(item.id, language)}</strong><StatusTag status={item.status} language={language} /></div>
            <div className="admin-case-meta">{tr("Account:")} <span className="admin-code">{shortId(item.user_id, language)}</span> · {friendlyDate(item.created_at, language)}</div>
            <p>{item.reason}</p>
            {item.status !== 'resolved' && <button type="button" className="secondary-action" disabled={caseBusy} onClick={() => void resolveCase(item)}>{tr("Mark Resolved")} <CheckCircle2 size={16} /></button>}
          </article>)}
          {!cases.length && !loading && !loadError && <div className="admin-empty"><HelpCircle size={23} /> {tr("No moderation cases recorded.")}</div>}
          <div className="admin-pagination"><span>{tr("Page")} {casesPage}</span><div><button type="button" className="secondary-action" disabled={casesPage === 1 || loading} onClick={() => setCasesPage(p => p - 1)}>{tr('Previous')}</button><button type="button" className="secondary-action" disabled={cases.length < 25 || loading} onClick={() => setCasesPage(p => p + 1)}>{tr('Next')}</button></div></div>
        </div>
      </div>
    </div>}

    {tab === 'audit' && <div className="admin-content"><div className="card admin-information-card">
      <h2><FileClock size={20} /> {tr("Admin Action History")}</h2>
      <p>{tr('Actions are recorded with their target account, reason and timestamp. Private user reports are never shown.')}</p>
      <div className="admin-audit-list">{audits.map(item => <article className="admin-audit-item" key={item.id}>
        <div><StatusTag status={item.action} language={language} /><span className="admin-audit-time"><Clock3 size={14} /> {friendlyDate(item.created_at, language)}</span></div>
        <p><strong>{tr("Target:")}</strong> <span className="admin-code">{shortId(item.target_user_id, language)}</span> <strong>{tr("Admin:")}</strong> <span className="admin-code">{shortId(item.admin_id, language)}</span></p><p>{item.reason}</p>
      </article>)}
      {!audits.length && !loading && !loadError && <div className="admin-empty">{tr('No admin moderation actions recorded yet.')}</div>}
      </div>
      <div className="admin-pagination"><span>{tr("Page")} {auditPage}</span><div><button className="secondary-action" type="button" disabled={auditPage === 1 || loading} onClick={() => setAuditPage(p => p - 1)}>{tr('Previous')}</button><button className="secondary-action" type="button" disabled={audits.length < 25 || loading} onClick={() => setAuditPage(p => p + 1)}>{tr('Next')}</button></div></div>
    </div></div>}
  </section>;
}
