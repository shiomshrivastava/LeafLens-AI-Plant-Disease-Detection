import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent, DragEvent, FormEvent } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import {
  ArrowLeft, ArrowRight, CheckCircle2, ChevronDown, CircleAlert, ClipboardList,
  Eye, EyeOff, FileImage, House, ImagePlus, Leaf, LockKeyhole, LogOut,
  Mail, Menu, PanelLeftClose, PanelLeftOpen, Save, ScanSearch, Settings, ShieldCheck, Sprout, Trash2, UploadCloud, BookOpen, Languages,
  UserRound, X, CloudSun, Shield,
} from 'lucide-react';
import { isConfigured, supabase } from './supabase';
import { AnalysisPanel } from './AnalysisPanel';
import type { AnalysisEntry, Report } from './AnalysisPanel';
import { CameraCapture } from './CameraCapture';
import { SensorPanel } from './SensorPanel';
import { AdminDashboard } from './AdminDashboard';
import { adminText } from './adminI18n';
import { CropsLibrary } from './CropsLibrary';
import { t, languageKey, loadLanguage } from './i18n';
import type { Language } from './i18n';

type AuthMode = 'login' | 'signup' | 'forgot' | 'update';
type Page = 'home' | 'results' | 'analyses' | 'profile' | 'settings' | 'crops' | 'weather' | 'admin';
type Notice = { type: 'success' | 'error'; text: string };
const apiUrl = (import.meta.env.VITE_AI_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const rememberKey = 'leaflens_remember_choice';
const sessionKey = 'leaflens_tab_session';
const sidebarKey = 'leaflens_sidebar_closed';

function Brand({ markOnly = false }: { markOnly?: boolean }) {
  return <span className="leaflens-brand"><span className="leaflens-brand-symbol"><Leaf size={25} strokeWidth={2.15} /></span>{!markOnly && <span>LeafLens</span>}</span>;
}
function DecorativeLeaf() {
  return <svg aria-hidden="true" className="outline-foliage" viewBox="0 0 370 550" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M80 540C86 400 198 310 257 62" stroke="currentColor" strokeWidth="1.5" />
    <path d="M255 63C183 89 146 145 151 213C217 197 264 151 255 63Z" stroke="currentColor" strokeWidth="1.6" />
    <path d="M154 209L255 63M177 184L164 135M194 158L234 147" stroke="currentColor" strokeWidth="1" />
    <path d="M197 310C266 278 322 279 352 311C325 360 260 377 197 310Z" stroke="currentColor" strokeWidth="1.5" />
    <path d="M197 310L352 311M248 316L274 290M291 315L307 342" stroke="currentColor" strokeWidth="1" />
    <path d="M115 435C61 385 22 376 4 390C17 456 60 478 115 435Z" stroke="currentColor" strokeWidth="1.6" />
    <path d="M115 435L4 390M78 431L64 395M51 418L38 449" stroke="currentColor" strokeWidth="1" />
  </svg>;
}
function displayName(user: User) {
  const fromProfile: unknown = user.user_metadata?.full_name;
  if (typeof fromProfile === 'string' && fromProfile.trim()) return fromProfile.trim().split(' ')[0];
  const username = (user.email || '').split('@')[0].replace(/[\d._-]+$/g, '').replace(/[._-]+/g, ' ').trim();
  if (!username) return 'there';
  return username[0].toUpperCase() + username.slice(1);
}

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [authMode, setAuthMode] = useState<AuthMode>('login');
  const [authError, setAuthError] = useState('');
  const [language, setLanguage] = useState<Language>(loadLanguage);
  const changeLanguage = (next: Language) => { setLanguage(next); localStorage.setItem(languageKey, next); };

  useEffect(() => {
    if (!supabase) { setInitializing(false); return; }
    const client = supabase;
    let active = true;
    client.auth.getSession().then(async ({ data, error }) => {
      if (!active) return;
      if (error) setAuthError(error.message);
      const shouldExpire = localStorage.getItem(rememberKey) === 'session' && sessionStorage.getItem(sessionKey) !== 'active';
      if (shouldExpire && data.session) {
        await client.auth.signOut();
        if (active) setSession(null);
      } else if (active) setSession(data.session);
    }).catch((e: unknown) => {
      if (active) setAuthError(e instanceof Error ? e.message : 'Unable to connect to authentication.');
    }).finally(() => { if (active) setInitializing(false); });
    const { data: { subscription } } = client.auth.onAuthStateChange((event, nextSession) => {
      if (!active) return;
      setSession(nextSession);
      if (event === 'PASSWORD_RECOVERY') setAuthMode('update');
    });
    return () => { active = false; subscription.unsubscribe(); };
  }, []);

  async function logout() {
    if (!supabase) return;
    const { error } = await supabase.auth.signOut();
    if (error) { setAuthError(error.message); return; }
    localStorage.removeItem(rememberKey);
    sessionStorage.removeItem(sessionKey);
    setAuthMode('login');
  }

  if (!isConfigured) return <main className="standalone-message"><Brand /><h1>Connect LeafLens to Supabase</h1><p>Check your existing <code>.env.local</code> file, then restart <code>npm run dev</code>. Add only your project's URL and publishable key, never a secret key.</p></main>;
  if (initializing) return <main className="standalone-message"><Brand /><div className="spinner" /><p>Connecting to your workspace…</p></main>;
  if (authMode === 'update') return <AuthView key="update" mode="update" onModeChange={setAuthMode} authError={authError} language={language} onLanguage={changeLanguage} />;
  return session ? <RoleWorkspace user={session.user} onLogout={logout} authError={authError} language={language} onLanguage={changeLanguage} /> : <AuthView key={authMode} mode={authMode} onModeChange={setAuthMode} authError={authError} language={language} onLanguage={changeLanguage} />;
}

/** Route by a verified backend role, not by an email/UID hardcoded in React. */
function RoleWorkspace({ user, onLogout, authError, language, onLanguage }: {
  user: User;
  onLogout: () => Promise<void>;
  authError: string;
  language: Language;
  onLanguage: (lang: Language) => void;
}) {
  const [role, setRole] = useState<'checking' | 'admin' | 'user' | 'unavailable'>('checking');
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let active = true;
    setRole('checking');
    async function checkRole() {
      try {
        if (!supabase) throw new Error('Supabase not configured');
        const { data, error } = await supabase.auth.getSession();
        if (error || !data.session?.access_token) throw new Error('Not authenticated');
        const response = await fetch(`${apiUrl}/api/admin/me`, {
          headers: { Authorization: `Bearer ${data.session.access_token}` },
        });
        if (!active) return;
        if (response.ok) setRole('admin');
        else if (response.status === 403) setRole('user');
        else setRole('unavailable'); // Do not mistakenly send admins to user UI on server errors.
      } catch {
        if (active) setRole('unavailable');
      }
    }
    void checkRole();
    return () => { active = false; };
  }, [user.id, retryKey]);

  if (role === 'admin') {
    return <div className="admin-only-scene">
      <header className="admin-only-header">
        <Brand />
        <span className="admin-only-label"><Shield size={16} /> {adminText(language, "Administrator Workspace")}</span>
        <div className="admin-only-actions">
          <LanguageToggle language={language} onLanguage={onLanguage} />
          <button type="button" className="toolbar-signout" onClick={() => void onLogout()}>
            <LogOut size={18} /><span>{adminText(language, "Sign out")}</span>
          </button>
        </div>
      </header>
      <main className="admin-only-content">
        {authError && <p className="auth-notice error" role="alert">{authError}</p>}
        <AdminDashboard ownUserId={user.id} language={language} />
      </main>
    </div>;
  }
  if (role === 'user') {
    return <Dashboard key={user.id} user={user} onLogout={onLogout}
      authError={authError} language={language} onLanguage={onLanguage} />;
  }
  return <main className="standalone-message" role="status">
    <Brand />
    {role === 'checking' ? <><div className="spinner" /><p>{adminText(language, "Checking your account access…")}</p></> : <>
      <h1>{adminText(language, "Account verification unavailable")}</h1>
      <p>{adminText(language, "Start your FastAPI backend and try again. Account access will not be assumed while the verification server is unavailable.")}</p>
      <div className="admin-only-retry-actions">
        <button type="button" className="primary-action" onClick={() => setRetryKey(v => v + 1)}>{adminText(language, "Retry connection")}</button>
        <button type="button" className="secondary-action" onClick={() => void onLogout()}>{adminText(language, "Sign out")}</button>
      </div>
    </>}
  </main>;
}

function AuthView({ mode, onModeChange, authError, language, onLanguage }: { mode: AuthMode; onModeChange: (mode: AuthMode) => void; authError: string; language: Language; onLanguage: (lang: Language) => void }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [visible, setVisible] = useState(false);
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const title = mode === 'signup' ? 'Create your account' : mode === 'forgot' ? 'Forgot password?' : mode === 'update' ? 'Set a new password' : 'Welcome back';
  const subtitle = mode === 'signup' ? 'Start your plant health journey with LeafLens.' : mode === 'forgot' ? 'We’ll send a password reset link to your email.' : mode === 'update' ? 'Choose a new secure password to continue.' : 'Sign in to continue to your plant health workspace';

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!supabase) return;
    setNotice(null);
    if ((mode === 'signup' || mode === 'update') && password !== confirm) { setNotice({ type: 'error', text: 'Passwords do not match.' }); return; }
    if (mode !== 'forgot' && password.length < 6) { setNotice({ type: 'error', text: 'Password must have at least 6 characters.' }); return; }
    setBusy(true);
    try {
      if (mode === 'login') {
        const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
        if (error) throw error;
        if (remember) { localStorage.setItem(rememberKey, 'persistent'); sessionStorage.removeItem(sessionKey); }
        else { localStorage.setItem(rememberKey, 'session'); sessionStorage.setItem(sessionKey, 'active'); }
      } else if (mode === 'signup') {
        const { data, error } = await supabase.auth.signUp({ email: email.trim(), password, options: { emailRedirectTo: window.location.origin, data: { full_name: name.trim() } } });
        if (error) throw error;
        setNotice({ type: 'success', text: data.session ? 'Account created successfully!' : 'Please check your email for the confirmation link before signing in.' });
      } else if (mode === 'forgot') {
        const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo: window.location.origin });
        if (error) throw error;
        setNotice({ type: 'success', text: 'If the email is registered, a recovery link will arrive shortly.' });
      } else {
        const { error } = await supabase.auth.updateUser({ password });
        if (error) throw error;
        setNotice({ type: 'success', text: 'Password updated. You can continue to your workspace.' });
      }
    } catch (err: unknown) {
      setNotice({ type: 'error', text: err instanceof Error ? err.message : 'An unexpected error occurred.' });
    } finally { setBusy(false); }
  }

  return <div className="login-scene">
    <DecorativeLeaf />
    <header className="login-brand"><Brand /></header>
    <div className="auth-language"><LanguageToggle language={language} onLanguage={onLanguage} /></div>
    <section className="login-story" aria-label="About LeafLens">
      <span className="story-eyebrow">HEALTHIER PLANTS<br />BRIGHTER TOMORROWS</span>
      <h1>Plant health<br />insights for<br />a greener world</h1>
      <p>{language === 'hi' ? 'LeafLens की मदद से AI द्वारा पौधों की सेहत समझें और उनकी देखभाल करें।' : 'LeafLens helps you understand, monitor, and care for your plants with the power of AI and real-world expertise.'}</p>
      <span className="story-accent" />
    </section>
    <div className="login-botanical" aria-hidden="true" />
    <div className="login-slogan" aria-hidden="true"><Leaf size={28} /><span>PLANTS<br />PEOPLE<br />A HEALTHIER PLANET</span></div>
    <main className="login-form-area">
      <section className="login-card" aria-label={`${title} form`}>
        <div className="login-card-logo"><Brand /></div>
        <div className="auth-heading"><h2>{t(language, title)}</h2><p>{t(language, subtitle)}</p></div>
        {authError && !notice && <div className="auth-notice error" role="alert">{authError}</div>}
        {notice && <div className={`auth-notice ${notice.type}`} role="status">{notice.text}</div>}
        <form onSubmit={submit} className="login-fields">
          {mode === 'signup' && <label className="login-label">{t(language, 'Full name')}<div className="login-input"><UserRound size={20} /><input type="text" autoComplete="name" required minLength={2} value={name} onChange={e => setName(e.target.value)} placeholder="Enter your full name" /></div></label>}
          {mode !== 'update' && <label className="login-label">{t(language, 'Email')}<div className="login-input"><Mail size={21} /><input type="email" required autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" /></div></label>}
          {mode !== 'forgot' && <label className="login-label">{t(language, mode === 'update' ? 'New password' : 'Password')}<div className="login-input"><LockKeyhole size={20} /><input type={visible ? 'text' : 'password'} minLength={6} required autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter your password" /><button type="button" className="password-toggle" onClick={() => setVisible(v => !v)} aria-label={visible ? 'Hide password' : 'Show password'}>{visible ? <EyeOff size={20} /> : <Eye size={20} />}</button></div></label>}
          {(mode === 'signup' || mode === 'update') && <label className="login-label">{t(language, 'Confirm password')}<div className="login-input"><LockKeyhole size={20} /><input type={visible ? 'text' : 'password'} minLength={6} required autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="Re-enter your password" /></div></label>}
          {mode === 'login' && <div className="login-options"><label className="remember-label"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} /><span>{t(language, 'Remember me')}</span></label><button type="button" className="link-button" onClick={() => onModeChange('forgot')}>{t(language, 'Forgot password?')}</button></div>}
          <button type="submit" className="primary-action login-submit" disabled={busy}>{t(language, busy ? 'Please wait…' : mode === 'signup' ? 'Create account' : mode === 'forgot' ? 'Send reset link' : mode === 'update' ? 'Update password' : 'Sign in')} <ArrowRight size={21} /></button>
        </form>
        <div className="login-bottom"><span>{t(language, mode === 'login' ? 'New here?' : mode === 'signup' ? 'Already have an account?' : mode === 'forgot' ? 'Remember your password?' : 'Password recovery')}</span>
          {mode !== 'update' && <button type="button" className="link-button" onClick={() => onModeChange(mode === 'login' ? 'signup' : 'login')}>{t(language, mode === 'login' ? 'Create account' : 'Sign in')}</button>}
        </div>
      </section>
    </main>
  </div>;
}

const supportedFeatures = [
  { title: 'Leaf Detection', desc: 'Checks if the image contains a usable leaf', icon: Leaf },
  { title: 'Crop Identification', desc: 'Identifies the plant species', icon: Sprout },
  { title: 'Disease Detection', desc: 'Detects and classifies plant diseases', icon: ShieldCheck },
  { title: 'Segmentation & Severity', desc: 'Highlights affected regions and estimates severity', icon: ScanSearch },
  { title: 'Plant Health Recommendations', desc: 'Offers simple crop care guidance based on disease and severity', icon: Sprout },
];

function Dashboard({ user, onLogout, authError, language, onLanguage }: { user: User; onLogout: () => Promise<void>; authError: string; language: Language; onLanguage: (lang: Language) => void }) {
  const [page, setPage] = useState<Page>('home');
  const [menuOpen, setMenuOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const urls = useRef<string[]>([]);
  const currentRequest = useRef<AbortController | null>(null);
  const [dragging, setDragging] = useState(false);
  const [fileError, setFileError] = useState('');
  const [analysisError, setAnalysisError] = useState('');
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<AnalysisEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');
  const [historyBusy, setHistoryBusy] = useState(false);
  const [transient, setTransient] = useState<AnalysisEntry | null>(null);
  const historySeq = useRef(0);
  const [sidebarClosed, setSidebarClosed] = useState(() => localStorage.getItem(sidebarKey) === '1');
  const [profileName, setProfileName] = useState(displayName(user));
  const [savedProfileName, setSavedProfileName] = useState(displayName(user));
  const [avatarPath, setAvatarPath] = useState<string | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarDraftUrl, setAvatarDraftUrl] = useState('');
  const [removeAvatarPending, setRemoveAvatarPending] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileNotice, setProfileNotice] = useState<Notice | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [settingsMessage, setSettingsMessage] = useState<Notice | null>(null);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [adminStatus, setAdminStatus] = useState<'checking' | 'admin' | 'normal' | 'error'>('checking');
  const name = savedProfileName.trim().split(/\s+/)[0] || displayName(user);
  const selected = history.find(x => x.id === activeId) ?? (transient?.id === activeId ? transient : undefined);

  function toggleSidebar() {
    if (window.innerWidth <= 870) { setMenuOpen(x => !x); return; }
    setSidebarClosed(x => { localStorage.setItem(sidebarKey, x ? '0' : '1'); return !x; });
  }

  async function sessionToken() {
    if (!supabase) throw new Error('Supabase is not configured.');
    const { data, error } = await supabase.auth.getSession();
    if (error || !data.session?.access_token) throw new Error('Your session expired. Please sign in again.');
    return data.session.access_token;
  }

  async function authorizedFetch(endpoint: string, options: RequestInit = {}) {
    const token = await sessionToken();
    return fetch(`${apiUrl}${endpoint}`, {
      ...options, headers: { ...(options.headers || {}), Authorization: `Bearer ${token}` },
    });
  }

  function toEntry(row: { id: string; image_name: string; image_url: string; created_at: string; report: Report }): AnalysisEntry {
    return {
      id: row.id, fileName: row.image_name, imageUrl: row.image_url,
      date: new Date(row.created_at).getTime(), report: row.report
    };
  }

  async function loadHistory() {
    const sequence = ++historySeq.current;
    setHistoryLoading(true); setHistoryError('');
    try {
      const response = await authorizedFetch('/api/analyses');
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `History server returned ${response.status}`);
      if (sequence === historySeq.current) {
        setHistory((data.items || []).map(toEntry));
      }
    } catch (e: unknown) {
      if (sequence === historySeq.current) setHistoryError(e instanceof Error ? e.message : 'Unable to load saved history.');
    } finally {
      if (sequence === historySeq.current) setHistoryLoading(false);
    }
  }

  async function loadProfile() {
    if (!supabase) return;
    const { data, error } = await supabase.from('profiles').select('display_name,avatar_path').eq('id', user.id).single();
    if (error) { setProfileNotice({ type: 'error', text: 'Could not load your profile: ' + error.message }); return; }
    setProfileName(data.display_name || displayName(user));
    setSavedProfileName(data.display_name || displayName(user));
    setAvatarPath(data.avatar_path || null);
    setRemoveAvatarPending(false);
    if (data.avatar_path) {
      const signed = await supabase.storage.from('avatars').createSignedUrl(data.avatar_path, 3600);
      if (signed.error) setProfileNotice({ type: 'error', text: 'Profile picture could not be loaded.' });
      else setAvatarUrl(signed.data.signedUrl);
    } else setAvatarUrl(null);
  }

  function chooseAvatar(event: ChangeEvent<HTMLInputElement>) {
    const item = event.target.files?.[0]; event.target.value = '';
    if (!item) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(item.type)) {
      setProfileNotice({ type: 'error', text: 'Use a JPG, PNG or WebP profile picture.' }); return;
    }
    if (item.size > 2 * 1024 * 1024) {
      setProfileNotice({ type: 'error', text: 'Profile picture must be 2 MB or smaller.' }); return;
    }
    if (avatarDraftUrl) URL.revokeObjectURL(avatarDraftUrl);
    setAvatarFile(item);
    setAvatarDraftUrl(URL.createObjectURL(item));
    setRemoveAvatarPending(false);
    setProfileNotice(null);
  }

  function removeProfilePhoto() {
    if (profileBusy) return;
    if (avatarDraftUrl) URL.revokeObjectURL(avatarDraftUrl);
    setAvatarFile(null);
    setAvatarDraftUrl('');
    setRemoveAvatarPending(Boolean(avatarPath));
    setProfileNotice({
      type: 'success',
      text: avatarPath
        ? 'Photo removed from preview. Click Save Changes to remove it from your account.'
        : 'Selected photo cleared.',
    });
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase || profileBusy) return;
    const client = supabase;
    const nextName = profileName.trim();
    if (nextName.length < 2 || nextName.length > 80) {
      setProfileNotice({ type: 'error', text: 'Display name must be 2–80 characters.' }); return;
    }
    setProfileBusy(true); setProfileNotice(null);
    let newPath: string | null = null;
    try {
      if (avatarFile) {
        const extension = avatarFile.type === 'image/png' ? 'png' : avatarFile.type === 'image/webp' ? 'webp' : 'jpg';
        newPath = `${user.id}/${crypto.randomUUID()}.${extension}`;
        const uploaded = await client.storage.from('avatars').upload(newPath, avatarFile, { contentType: avatarFile.type, upsert: false });
        if (uploaded.error) throw uploaded.error;
      }
      // Null is intentional when Remove photo was selected; don't fall back to the old path.
      const nextAvatarPath = removeAvatarPending ? null : (newPath ?? avatarPath);
      const updated = await client.from('profiles')
        .update({ display_name: nextName, avatar_path: nextAvatarPath })
        .eq('id', user.id).select('id').single();
      if (updated.error) throw updated.error;

      // Commit the profile first so deleting the old file cannot break the saved record.
      if (newPath) {
        const signed = await client.storage.from('avatars').createSignedUrl(newPath, 3600);
        setAvatarUrl(signed.error ? null : signed.data.signedUrl);
        setAvatarPath(newPath);
        setAvatarFile(null);
        if (avatarDraftUrl) URL.revokeObjectURL(avatarDraftUrl);
        setAvatarDraftUrl('');
      } else if (removeAvatarPending) {
        setAvatarPath(null);
        setAvatarUrl(null);
        setRemoveAvatarPending(false);
      }

      let cleanupWarning = false;
      if (avatarPath && avatarPath !== nextAvatarPath) {
        try {
          const removed = await client.storage.from('avatars').remove([avatarPath]);
          if (removed.error) throw removed.error;
        } catch (cleanupError) {
          cleanupWarning = true;
          console.warn('Old avatar cleanup failed:', cleanupError);
        }
      }
      setSavedProfileName(nextName);
      setProfileNotice({
        type: cleanupWarning ? 'error' : 'success',
        text: cleanupWarning
          ? 'Profile updated, but the old photo could not be removed from Storage. Please check Storage permissions.'
          : 'Your profile changes have been saved.',
      });
    } catch (e: unknown) {
      if (newPath) await client.storage.from('avatars').remove([newPath]);
      setProfileNotice({ type: 'error', text: e instanceof Error ? e.message : 'Unable to save your profile.' });
    } finally { setProfileBusy(false); }
  }

  async function deleteOne(entry: AnalysisEntry) {
    if (!window.confirm(`Permanently delete ${entry.fileName} and its saved images? This cannot be undone.`)) return;
    setHistoryBusy(true); setHistoryError('');
    try {
      const res = await authorizedFetch(`/api/analyses/${encodeURIComponent(entry.id)}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Delete failed.');
      setHistory(items => items.filter(x => x.id !== entry.id));
      if (activeId === entry.id) { setActiveId(null); setTransient(null); changePage('analyses'); }
    } catch (e: unknown) { setHistoryError(e instanceof Error ? e.message : 'Deletion failed.'); }
    finally { setHistoryBusy(false); }
  }

  async function deleteAll() {
    if (!history.length || !window.confirm('Permanently delete ALL saved analyses and their images? This cannot be undone.')) return;
    setHistoryBusy(true); setHistoryError('');
    try {
      const res = await authorizedFetch('/api/analyses', { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Could not clear history.');
      setHistory([]); setActiveId(null); setTransient(null); changePage('analyses');
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Unable to clear history.';
      await loadHistory();
      setHistoryError(message);
    } finally { setHistoryBusy(false); }
  }

  useEffect(() => {
    // Admin authority is verified by the protected backend, never browser metadata.
    let alive = true;
    setAdminStatus('checking');
    async function checkAdmin() {
      try {
        const response = await authorizedFetch('/api/admin/me');
        if (!alive) return;
        if (response.ok) setAdminStatus('admin');
        else if (response.status === 403 || response.status === 401) setAdminStatus('normal');
        else setAdminStatus('error');
      } catch { if (alive) setAdminStatus('error'); }
    }
    void checkAdmin();
    return () => { alive = false; };
    // Recheck if the authenticated account changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.id]);

  useEffect(() => {
    if (page === 'admin' && adminStatus !== 'admin') setPage('home');
  }, [page, adminStatus]);

  useEffect(() => {
    void loadHistory();
    void loadProfile();
    return () => { currentRequest.current?.abort(); urls.current.forEach(url => URL.revokeObjectURL(url)); };
    // User identity is stable for this mounted dashboard.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.id]);

  function changePage(next: Page) { setPage(next); setMenuOpen(false); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  function acceptFile(next: File | undefined) {
    setFileError(''); setAnalysisError('');
    if (!next) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(next.type)) { setFileError('Use JPG, PNG or WebP images only.'); return; }
    if (next.size > 10 * 1024 * 1024) { setFileError('Maximum file size is 10 MB.'); return; }
    const url = URL.createObjectURL(next);
    urls.current.push(url);
    setPreview(url);
    setFile(next);
  }
  function fileChanged(event: ChangeEvent<HTMLInputElement>) { acceptFile(event.target.files?.[0]); event.target.value = ''; }
  function dropped(event: DragEvent<HTMLDivElement>) { event.preventDefault(); setDragging(false); acceptFile(event.dataTransfer.files[0]); }

  async function analyze() {
    if (!file || !preview || busy) return;
    setAnalysisError('');
    setBusy(true);
    const controller = new AbortController();
    currentRequest.current = controller;
    try {
      const payload = new FormData(); payload.append('file', file);
      const response = await authorizedFetch('/api/analyze', { method: 'POST', body: payload, signal: controller.signal });
      const data: unknown = await response.json();
      if (!response.ok) {
        const detail = data && typeof data === 'object' && 'detail' in data ? String(data.detail) : `HTTP ${response.status}`;
        throw new Error(detail);
      }
      if (controller.signal.aborted) return;
      const report = data as Report;
      if (!report.decision || !Array.isArray(report.stage_summary)) throw new Error('The backend returned an incomplete analysis report.');
      const entry: AnalysisEntry = { id: report.saved_analysis_id || crypto.randomUUID(), fileName: file.name, imageUrl: preview, date: Date.now(), report };
      setTransient(entry);
      if (report.saved_analysis_id) {
        setHistory(items => [entry, ...items.filter(x => x.id !== entry.id)].slice(0, 10));
        void loadHistory();
      }
      setActiveId(entry.id);
      // The result keeps its own imageUrl, so the saved report/preview stays intact.
      // Reset only the upload form after a successful response (including rejections).
      // Leave the blob URL alive: the current result may still display that image.
      setFile(null);
      setPreview('');
      setFileError('');
      setDragging(false);
      changePage('results');
    } catch (err: unknown) {
      if (!controller.signal.aborted) setAnalysisError(err instanceof Error ? err.message : 'Unable to reach the AI analysis server.');
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }

  async function resetPassword() {
    if (!supabase || !user.email) return;
    setSettingsBusy(true); setSettingsMessage(null);
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(user.email, { redirectTo: window.location.origin });
      if (error) throw error;
      setSettingsMessage({ type: 'success', text: 'A password reset link has been sent to your registered email.' });
    } catch (err: unknown) { setSettingsMessage({ type: 'error', text: err instanceof Error ? err.message : 'Unable to send reset email.' }); }
    finally { setSettingsBusy(false); }
  }

  return <div className={`dashboard-scene ${sidebarClosed ? 'sidebar-collapsed' : ''}`}>
    <DecorativeLeaf />
    <button type="button" className="mobile-menu" onClick={() => setMenuOpen(x => !x)} aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}>{menuOpen ? <X size={23} /> : <Menu size={23} />}</button>
    {menuOpen && <div className="sidebar-scrim" onClick={() => setMenuOpen(false)} />}
    <aside className={`app-sidebar ${menuOpen ? 'sidebar-visible' : ''}`} aria-hidden={sidebarClosed && !menuOpen}>
      <div className="sidebar-logo"><Brand /></div>
      <nav className="sidebar-navigation" aria-label="Main navigation">
        {([
          ['home', House, 'Home'], ['analyses', ClipboardList, 'My Analyses'],
          ['crops', BookOpen, 'Supported Crops'], ['weather', CloudSun, 'Weather'],
          ['profile', UserRound, 'Profile'], ['settings', Settings, 'Settings'],
          ...(adminStatus === 'admin' ? [['admin', Shield, 'Admin Dashboard'] as const] : []),
        ] as const).map(([target, Icon, label]) => <button type="button" key={target} className={`sidebar-link ${page === target || (page === 'results' && target === 'analyses') ? 'selected' : ''}`} onClick={() => changePage(target)}><Icon size={20} /><span>{t(language, label)}</span></button>)}
      </nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-motto"><Leaf size={22} /><strong>{t(language, 'Plant Health')}</strong><p>{t(language, 'For a sustainable tomorrow.')}</p></div>
      <button type="button" className="sidebar-logout" onClick={() => void onLogout()}><LogOut size={19} /> {t(language, 'Log out')}</button>
    </aside>

    <div className="dashboard-main">
      <header className="dashboard-toolbar"><div className="toolbar-left"><button type="button" className="sidebar-toggle" onClick={toggleSidebar} aria-label={sidebarClosed ? 'Expand sidebar' : 'Collapse sidebar'} title={sidebarClosed ? 'Expand sidebar' : 'Collapse sidebar'}>{sidebarClosed ? <PanelLeftOpen size={22} /> : <PanelLeftClose size={22} />}</button><div className="toolbar-breadcrumb"><span>LeafLens</span><span className="breadcrumb-sep">/</span><span>{t(language, page === 'results' ? 'Analysis Results' : page === 'analyses' ? 'My Analyses' : page === 'crops' ? 'Supported Crops' : page === 'weather' ? 'Weather' : page === 'profile' ? 'Profile' : page === 'settings' ? 'Settings' : page === 'admin' ? 'Admin Dashboard' : 'Home')}</span></div></div><div className="toolbar-right"><LanguageToggle language={language} onLanguage={onLanguage} /><button className="toolbar-account" type="button" onClick={() => changePage('profile')} aria-label="Go to your profile"><span className="account-avatar">{avatarUrl ? <img src={avatarUrl} alt="" /> : name[0]?.toUpperCase() || 'U'}</span><span>{name}</span><ChevronDown size={18} /></button><button type="button" className="toolbar-signout" onClick={() => void onLogout()} title="Sign out" aria-label="Sign out of LeafLens"><LogOut size={18} /><span>{adminText(language, "Sign out")}</span></button></div></header>
      {authError && <p className="auth-notice error" role="alert">{authError}</p>}
      {page === 'admin' && adminStatus === 'admin' && <AdminDashboard ownUserId={user.id} language={language} onBack={() => changePage('home')} />}
      {page === 'home' && <div className="home-page">
        <div className="page-heading home-title"><h1>{language === 'hi' ? 'नमस्ते' : 'Welcome'}, {name} <span className="wave">👋</span></h1><p>{t(language, 'Upload a leaf image to analyze plant health using AI.')}</p></div>
        <div className="home-grid">
          <section className="card upload-card" aria-label="Upload an image">
            <div className={`upload-dropzone ${dragging ? 'dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={event => { event.preventDefault(); setDragging(false); }} onDrop={dropped}>
              <input className="sr-only" id="leaf-image-input" type="file" accept="image/jpeg,image/png,image/webp" onChange={fileChanged} />
              {preview ? <div className="chosen-leaf"><div className="chosen-leaf-preview"><img src={preview} alt="Selected leaf preview" /></div><div className="chosen-leaf-meta"><FileImage size={17} /><span title={file?.name}>{file?.name}</span></div><label className="secondary-action" htmlFor="leaf-image-input"><ImagePlus size={17} /> {t(language, 'Change image')}</label></div> : <div className="upload-empty"><div className="upload-emblem"><UploadCloud size={43} /></div><h2>{t(language, 'Upload a Leaf Image')}</h2><p>{t(language, 'Drag and drop an image here, or click to select')}</p><span>JPG, PNG, WebP · Up to 10 MB</span><label className="primary-action select-image" htmlFor="leaf-image-input"><ImagePlus size={18} /> {t(language, 'Choose Image')}</label></div>}
            </div>
            <div className="camera-upload-action"><CameraCapture onCapture={acceptFile} language={language} disabled={busy} /></div>
            {fileError && <p className="inline-error" role="alert"><CircleAlert size={17} />{fileError}</p>}
            {file && <div className="upload-actions"><span><CheckCircle2 size={16} /> {t(language, 'Ready for analysis')}</span><button className="primary-action analyze-now" type="button" disabled={busy} onClick={() => void analyze()}>{busy ? <><span className="spinner mini" /> {t(language, 'Analyzing…')}</> : <>{t(language, 'Analyze Leaf')} <ArrowRight size={17} /></>}</button></div>}
            {busy && <p className="analysis-working" role="status">{t(language, 'Checking your leaf photo. This may take a few moments.')}</p>}
            {analysisError && <div className="inline-error" role="alert"><CircleAlert size={18} /><span><strong>Analysis failed.</strong> {analysisError}<small>{t(language, 'Check the Python FastAPI terminal and try again.')}</small></span></div>}
          </section>
          <section className="card features-card"><h2>{t(language, 'Supported Features')}</h2><div className="features-list">{supportedFeatures.map(({ title, desc, icon: Icon }) => <div className="feature-row" key={title}><span className="feature-icon"><Icon size={24} /></span><div><strong>{t(language, title)}</strong><p>{t(language, desc)}</p></div></div>)}</div></section>
        </div>
        <section className="card how-card"><div className="how-heading"><h2>{t(language, 'How It Works')}</h2><p>{t(language, 'From a leaf photo to helpful care tips in three easy steps.')}</p></div><div className="how-steps"><div><span className="step-count">1</span><span><strong>{t(language, 'Add a Leaf Photo')}</strong><small>{t(language, 'Upload a photo or take one with your camera.')}</small></span></div><div><span className="step-count">2</span><span><strong>{t(language, 'Check Leaf Health')}</strong><small>{t(language, 'See possible problems and highlighted areas.')}</small></span></div><div><span className="step-count">3</span><span><strong>{t(language, 'Get Care Guidance')}</strong><small>{t(language, 'Read care tips, save results and download your report.')}</small></span></div></div></section>
      </div>}
      {page === 'results' && (selected ? <AnalysisPanel entry={selected} onBack={() => changePage('home')} language={language} /> : <EmptyState heading="No analysis selected" text="Upload a photo first to view its AI results." onGo={() => changePage('home')} />)}
      {page === 'crops' && <CropsLibrary language={language} />}
      {page === 'weather' && <div className="weather-full-page"><div className="page-heading"><h1>{language === 'hi' ? 'मौसम और सेंसर' : 'Weather & Sensor Monitoring'}</h1><p>{language === 'hi' ? 'स्थानीय DHT11 सेंसर और आपके चुने स्थान का मौसम पूर्वानुमान।' : 'Your local DHT11 sensor and location-based outdoor weather forecasts.'}</p></div><SensorPanel apiBaseUrl={apiUrl} language={language} userId={user.id} /></div>}
      {page === 'analyses' && <section className="secondary-page">
        <div className="page-heading history-heading"><div><h1>{t(language, 'My Analyses')}</h1><p>{language === 'hi' ? 'आपके आख़िरी 10 विश्लेषण, लॉगिन और पेज रीफ्रेश के बाद भी उपलब्ध।' : 'Your latest 10 saved analyses, available across logins and page reloads.'}</p></div>
          {history.length > 0 && <button className="danger-action" type="button" disabled={historyBusy} onClick={() => void deleteAll()}><Trash2 size={17} /> {t(language, historyBusy ? 'Working…' : 'Clear All History')}</button>}</div>
        {historyError && <div className="auth-notice error" role="alert">{historyError} <button type="button" className="link-button" onClick={() => void loadHistory()}>Retry</button></div>}
        {historyLoading && <p className="history-loading"><span className="spinner mini" /> {t(language, 'Loading saved analyses…')}</p>}
        <div className="card analyses-list">{history.length ? history.map(entry => <div className="history-row" key={entry.id}>
          <button className="history-entry" onClick={() => { setActiveId(entry.id); changePage('results'); }}><img src={entry.imageUrl} alt="Uploaded leaf" /><span><strong>{entry.report.model0c?.predicted_crop || 'Leaf analysis'} · {entry.report.model2?.disease || entry.report.model1?.status || entry.report.decision.replace(/_/g, ' ')}</strong><small>{entry.fileName} · {new Date(entry.date).toLocaleString()}</small>{entry.report.recommendations && <small className="history-care-preview"><Sprout size={13} />{language === 'hi' ? entry.report.recommendations.title_hi : entry.report.recommendations.title_en}: {(language === 'hi' ? entry.report.recommendations.tips_hi : entry.report.recommendations.tips_en)[0]}</small>}</span><ArrowRight size={18} /></button>
          <button type="button" className="history-trash" aria-label={`Delete ${entry.fileName}`} title="Delete this analysis" disabled={historyBusy} onClick={() => void deleteOne(entry)}><Trash2 size={19} /></button>
        </div>) : !historyLoading && !historyError ? <div className="empty-history"><ClipboardList size={32} /><h2>{t(language, 'No saved analyses yet')}</h2><p>{t(language, 'Analyze a leaf to save your first result here.')}</p><button className="primary-action" onClick={() => changePage('home')}>{t(language, 'Analyze a leaf')} <ArrowRight size={16} /></button></div> : null}</div>
        <p className="small-note">{t(language, 'Only the latest 10 successful analyses are kept. Older records and stored images are removed automatically.')}</p>
      </section>}
      {page === 'profile' && <section className="secondary-page"><div className="page-heading"><h1>{t(language, 'My Profile')}</h1><p>{t(language, 'Edit your display name and profile picture.')}</p></div>
        <form className="card profile-form" onSubmit={e => void saveProfile(e)}>
          <div className="profile-picture-row">
            <span className="profile-avatar profile-photo" aria-label="Current profile picture">
              {!removeAvatarPending && (avatarDraftUrl || avatarUrl)
                ? <img src={avatarDraftUrl || avatarUrl || ''} alt="Your profile picture" />
                : (profileName.trim()[0] || name[0] || 'U').toUpperCase()}
            </span>
            <div className="profile-photo-details">
              <h2>{t(language, 'Profile photo')}</h2>
              <p>JPG, PNG or WebP · Maximum 2 MB</p>
              <div className="profile-photo-actions">
                <label htmlFor="profile-photo-input" className={`secondary-action profile-upload ${profileBusy ? 'disabled-action' : ''}`}><ImagePlus size={17} /> {t(language, avatarPath || avatarFile ? 'Change photo' : 'Choose photo')}</label>
                <input className="sr-only" type="file" id="profile-photo-input" accept="image/jpeg,image/png,image/webp" onChange={chooseAvatar} disabled={profileBusy} />
                {(avatarPath || avatarFile) && !removeAvatarPending && (
                  <button type="button" className="secondary-action profile-remove" disabled={profileBusy} onClick={removeProfilePhoto}>
                    <Trash2 size={17} /> {t(language, 'Remove photo')}
                  </button>
                )}
              </div>
              {removeAvatarPending && <p className="profile-pending-note">{t(language, 'Click Save Changes to permanently remove the saved photo.')}</p>}
            </div>
          </div>
          <label className="profile-field">{t(language, 'Display name')}<input value={profileName} maxLength={80} minLength={2} required onChange={e => setProfileName(e.target.value)} placeholder="Your full name" /></label>
          <label className="profile-field">{t(language, 'Account email')}<input value={user.email || ''} disabled readOnly /><small>{t(language, 'Email is managed by Supabase Authentication.')}</small></label>
          {profileNotice && <div className={`auth-notice ${profileNotice.type}`} role="status">{profileNotice.text}</div>}
          <button className="primary-action profile-save" type="submit" disabled={profileBusy}><Save size={17} />{t(language, profileBusy ? 'Saving…' : 'Save Changes')}</button>
        </form>
      </section>}
      {page === 'settings' && <section className="secondary-page"><div className="page-heading"><h1>{t(language, 'Settings')}</h1><p>{t(language, 'Account security and preferences.')}</p></div><div className="card settings-card"><div><h2>{t(language, 'Account security')}</h2><p>{t(language, 'Send a password-reset link to your registered email address.')}</p><strong>{user.email}</strong></div><button type="button" className="primary-action" disabled={settingsBusy} onClick={() => void resetPassword()}>{t(language, settingsBusy ? 'Sending…' : 'Send reset link')} <ArrowRight size={17} /></button></div>{settingsMessage && <div className={`auth-notice ${settingsMessage.type}`} role="status">{settingsMessage.text}</div>}{adminStatus === 'error' && <p className="small-note">Admin access check unavailable. Verify the backend is running and its admin service configured, then refresh the page.</p>}</section>}
    </div>
  </div>;
}

function EmptyState({ heading, text, onGo }: { heading: string; text: string; onGo: () => void }) {
  return <section className="card empty-state"><Leaf size={35} /><h2>{heading}</h2><p>{text}</p><button type="button" className="primary-action" onClick={onGo}><ArrowLeft size={16} /> Back to Home</button></section>;
}

function LanguageToggle({ language, onLanguage }: { language: Language; onLanguage: (next: Language) => void }) {
  return <div className="language-toggle" role="group" aria-label="Language / भाषा">
    <Languages size={16} aria-hidden="true" />
    <button type="button" className={language === 'en' ? 'active' : ''} aria-pressed={language === 'en'} onClick={() => onLanguage('en')}>EN</button>
    <span className="lang-divider">/</span>
    <button type="button" className={language === 'hi' ? 'active' : ''} aria-pressed={language === 'hi'} onClick={() => onLanguage('hi')}>हिंदी</button>
  </div>;
}
