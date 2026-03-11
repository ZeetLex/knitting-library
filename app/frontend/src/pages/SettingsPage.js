/**
 * SettingsPage.js
 * User settings (appearance, account, data) + admin panel (users, logs, mail, 2FA).
 * Admin sections are only rendered when user.is_admin === true.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Sun, Moon, Globe, Lock, Users, Plus, Trash2, KeyRound, X,
  ChevronLeft, Download, LogOut, Terminal, Mail, ShieldCheck,
  RefreshCw, Send, CheckCircle, XCircle, Smartphone,
} from 'lucide-react';
import { useApp } from '../utils/AppContext';
import {
  changePassword, fetchUsers, createUser, deleteUser, adminResetPassword, exportLibrary,
  fetchLogs, fetchMailSettings, saveMailSettings, testMail,
  fetch2FAStatus, adminReset2FA, setup2FA, verify2FASetup, disable2FA,
} from '../utils/api';
import './SettingsPage.css';

export default function SettingsPage({ onBack }) {
  const { user, t } = useApp();
  const [activeSection, setActiveSection] = useState('appearance');

  const navItems = [
    { id: 'appearance', icon: <Sun size={18} />,        label: t('appearance') },
    { id: 'account',    icon: <Lock size={18} />,       label: t('account') },
    { id: 'data',       icon: <Download size={18} />,   label: t('dataSection') },
    ...(user?.is_admin ? [
      { id: 'users',    icon: <Users size={18} />,       label: t('userManagement'), adminDivider: true },
      { id: 'logs',     icon: <Terminal size={18} />,    label: t('adminLogs') },
      { id: 'mail',     icon: <Mail size={18} />,        label: t('adminMail') },
      { id: 'twofa',    icon: <ShieldCheck size={18} />, label: t('admin2FA') },
    ] : []),
  ];

  return (
    <div className="settings-page">
      <div className="settings-topbar">
        <button className="settings-back" onClick={onBack}>
          <ChevronLeft size={20} />
          <span>{t('backToLibrary')}</span>
        </button>
        <h2 className="settings-title">{t('settings')}</h2>
        <div style={{ width: 80 }} />
      </div>

      <div className="settings-body">
        <nav className="settings-nav">
          {navItems.map((item, i) => (
            <React.Fragment key={item.id}>
              {item.adminDivider && (
                <div className="settings-nav-divider">
                  <span>{t('adminPanel')}</span>
                </div>
              )}
              <button
                className={`settings-nav-btn ${activeSection === item.id ? 'active' : ''}`}
                onClick={() => setActiveSection(item.id)}
              >
                {item.icon}
                {item.label}
              </button>
            </React.Fragment>
          ))}
        </nav>

        <div className="settings-content">
          {activeSection === 'appearance' && <AppearanceSection />}
          {activeSection === 'account'    && <AccountSection />}
          {activeSection === 'data'       && <DataSection />}
          {user?.is_admin && activeSection === 'users' && <UsersSection />}
          {user?.is_admin && activeSection === 'logs'  && <LogsSection />}
          {user?.is_admin && activeSection === 'mail'  && <MailSection />}
          {user?.is_admin && activeSection === 'twofa' && <TwoFASection />}
        </div>
      </div>
    </div>
  );
}

/* ─── Appearance Section ──────────────────────────────────────────────────── */

const COLOUR_THEMES = [
  { id: 'terracotta', labelKey: 'themeTerracotta', bg: '#f5f0e8', card: '#ffffff', accent: '#c4714a', bgDark: '#1c1410', cardDark: '#221810', accentDark: '#d4876a', flowerColour: '#c4714a', flowerColourDark: '#d4876a' },
  { id: 'rose',       labelKey: 'themeRose',       bg: '#fdf5f6', card: '#ffffff', accent: '#c2637a', bgDark: '#1e1216', cardDark: '#241418', accentDark: '#e08898', flowerColour: '#c2637a', flowerColourDark: '#e08898' },
  { id: 'lavender',   labelKey: 'themeLavender',   bg: '#f7f4fc', card: '#ffffff', accent: '#8b6cae', bgDark: '#16121e', cardDark: '#1c1626', accentDark: '#b094d4', flowerColour: '#8b6cae', flowerColourDark: '#b094d4' },
  { id: 'sage',       labelKey: 'themeSage',       bg: '#f4f7f3', card: '#ffffff', accent: '#5a8c6a', bgDark: '#111a13', cardDark: '#152018', accentDark: '#7aaa8a', flowerColour: '#5a8c6a', flowerColourDark: '#7aaa8a' },
  { id: 'berry',      labelKey: 'themeBerry',      bg: '#fcf4fa', card: '#ffffff', accent: '#8e3a6e', bgDark: '#1a1020', cardDark: '#201226', accentDark: '#c874a8', flowerColour: '#8e3a6e', flowerColourDark: '#c874a8' },
];

function ThemeSwatch({ themeData, isSelected, isDark, onClick }) {
  const bg     = isDark ? themeData.bgDark     : themeData.bg;
  const card   = isDark ? themeData.cardDark   : themeData.card;
  const accent = isDark ? themeData.accentDark : themeData.accent;
  const fc     = isDark ? themeData.flowerColourDark : themeData.flowerColour;

  return (
    <button className={`theme-swatch ${isSelected ? 'selected' : ''}`} onClick={onClick} aria-label={themeData.id}>
      <div className="swatch-preview" style={{ background: bg }}>
        <div className="swatch-header" style={{ background: card, borderBottom: `1px solid ${accent}22` }}>
          <div className="swatch-dot" style={{ background: accent }} />
          <div className="swatch-line short" style={{ background: accent + '55' }} />
        </div>
        <div className="swatch-grid">
          {[0,1,2,3].map(i => (
            <div key={i} className="swatch-card" style={{ background: card, boxShadow: `0 1px 4px ${accent}22` }}>
              {i === 0 && (
                <svg viewBox="0 0 20 20" width="14" height="14" style={{ margin: '2px auto', display: 'block' }}>
                  <circle cx="10" cy="10" r="3" fill={fc} opacity="0.9" />
                  <circle cx="10" cy="4"  r="2.5" fill={fc} opacity="0.55" />
                  <circle cx="10" cy="16" r="2.5" fill={fc} opacity="0.55" />
                  <circle cx="4"  cy="10" r="2.5" fill={fc} opacity="0.55" />
                  <circle cx="16" cy="10" r="2.5" fill={fc} opacity="0.55" />
                </svg>
              )}
              <div className="swatch-line" style={{ background: accent + '33', marginTop: i === 0 ? 2 : 6 }} />
              <div className="swatch-line short" style={{ background: accent + '22' }} />
            </div>
          ))}
        </div>
        <div className="swatch-accent-bar" style={{ background: accent }} />
      </div>
      {isSelected && (
        <div className="swatch-check" style={{ background: accent }}>
          <svg viewBox="0 0 12 12" width="10" height="10">
            <polyline points="2,6 5,9 10,3" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
      )}
    </button>
  );
}

function AppearanceSection() {
  const { theme, colourTheme, language, currency, t, updateSettings } = useApp();
  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('appearance')}</h3>
      <div className="settings-row settings-row--column">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('colourTheme')}</p>
          <p className="settings-row-sub">{t('colourThemeSub')}</p>
        </div>
        <div className="theme-swatch-grid">
          {COLOUR_THEMES.map(ct => (
            <div key={ct.id} className="theme-swatch-wrap">
              <ThemeSwatch themeData={ct} isSelected={colourTheme === ct.id} isDark={theme === 'dark'}
                onClick={() => updateSettings(theme, language, currency, ct.id)} />
              <span className="swatch-label">{t(ct.labelKey)}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="settings-row">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('darkMode')}</p>
          <p className="settings-row-sub">{theme === 'dark' ? t('darkMode') : t('lightMode')}</p>
        </div>
        <button className={`theme-toggle ${theme === 'dark' ? 'dark' : ''}`}
          onClick={() => updateSettings(theme === 'dark' ? 'light' : 'dark', language, currency, colourTheme)}>
          <span className="theme-toggle-knob">{theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}</span>
        </button>
      </div>
      <div className="settings-row">
        <div className="settings-row-info"><p className="settings-row-label">{t('language')}</p></div>
        <div className="lang-switcher">
          <button className={`lang-btn ${language === 'en' ? 'active' : ''}`} onClick={() => updateSettings(theme, 'en', currency, colourTheme)}>🇬🇧 English</button>
          <button className={`lang-btn ${language === 'no' ? 'active' : ''}`} onClick={() => updateSettings(theme, 'no', currency, colourTheme)}>🇳🇴 Norsk</button>
        </div>
      </div>
      <div className="settings-row">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('currency')}</p>
          <p className="settings-row-sub">{t('currencySub')}</p>
        </div>
        <div className="lang-switcher">
          {[{ code:'NOK', label:'kr' }, { code:'USD', label:'$' }, { code:'GBP', label:'£' }].map(c => (
            <button key={c.code} className={`lang-btn ${currency === c.code ? 'active' : ''}`}
              onClick={() => updateSettings(theme, language, c.code, colourTheme)}>
              {c.label} {c.code}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── Account Section ─────────────────────────────────────────────────────── */
function AccountSection() {
  const { user, t, logout } = useApp();
  const [oldPw, setOldPw]       = useState('');
  const [newPw, setNewPw]       = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [status, setStatus]     = useState(null);
  const [saving, setSaving]     = useState(false);

  // 2FA self-service state
  const [totpSetup, setTotpSetup] = useState(null);  // { secret, qr_code }
  const [totpCode, setTotpCode]   = useState('');
  const [totpStatus, setTotpStatus] = useState(null);
  const [disablePw, setDisablePw] = useState('');
  const [showDisable, setShowDisable] = useState(false);

  const handlePasswordSubmit = async () => {
    if (!oldPw || !newPw || !confirmPw) return;
    if (newPw !== confirmPw) { setStatus('error:' + t('passwordMismatch')); return; }
    if (newPw.length < 4)   { setStatus('error:' + t('passwordTooShort')); return; }
    setSaving(true); setStatus(null);
    try {
      await changePassword(oldPw, newPw);
      setStatus('success');
      setOldPw(''); setNewPw(''); setConfirmPw('');
    } catch (e) { setStatus('error:' + e.message); }
    finally { setSaving(false); }
  };

  const handleSetup2FA = async () => {
    setTotpStatus(null);
    try {
      const data = await setup2FA();
      setTotpSetup(data);
      setTotpCode('');
    } catch (e) { setTotpStatus('error:' + e.message); }
  };

  const handleVerify2FA = async () => {
    setTotpStatus(null);
    try {
      await verify2FASetup(totpCode);
      setTotpStatus('success');
      setTotpSetup(null);
    } catch (e) { setTotpStatus('error:' + e.message); setTotpCode(''); }
  };

  const handleDisable2FA = async () => {
    try {
      await disable2FA(disablePw);
      setShowDisable(false);
      setDisablePw('');
      setTotpStatus('disabled');
    } catch (e) { setTotpStatus('error:' + e.message); }
  };

  const isError  = status?.startsWith('error:');
  const errorMsg = isError ? status.slice(6) : '';
  const totpIsError = totpStatus?.startsWith('error:');
  const totpErrMsg  = totpIsError ? totpStatus.slice(6) : '';

  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('account')}</h3>
      <div className="user-badge">
        <div className="user-badge-avatar">{user?.username?.[0]?.toUpperCase()}</div>
        <div>
          <p className="user-badge-name">{user?.username}</p>
          <p className="user-badge-role">{user?.is_admin ? t('admin') : t('member')}</p>
        </div>
      </div>

      <h4 className="subsection-heading">{t('changePassword')}</h4>
      <div className="form-stack">
        <div className="form-field">
          <label className="form-label">{t('currentPassword')}</label>
          <input type="password" className="form-input" value={oldPw} onChange={e => setOldPw(e.target.value)} autoComplete="current-password" />
        </div>
        <div className="form-field">
          <label className="form-label">{t('newPassword')}</label>
          <input type="password" className="form-input" value={newPw} onChange={e => setNewPw(e.target.value)} autoComplete="new-password" />
        </div>
        <div className="form-field">
          <label className="form-label">{t('confirmNewPassword')}</label>
          <input type="password" className="form-input" value={confirmPw} onChange={e => setConfirmPw(e.target.value)} autoComplete="new-password" />
        </div>
        {status === 'success' && <p className="status-success">{t('passwordChanged')}</p>}
        {isError && <p className="status-error">{errorMsg}</p>}
        <button className="btn-primary" onClick={handlePasswordSubmit} disabled={saving || !oldPw || !newPw || !confirmPw}>
          {saving ? t('saving') : t('savePassword')}
        </button>
      </div>

      {/* ── 2FA self-service ─────────────────────────────────────────── */}
      <h4 className="subsection-heading" style={{ marginTop: '2rem' }}>{t('twoFA')}</h4>
      <div className="form-stack">
        {totpStatus === 'success' && <p className="status-success">{t('twoFAEnabled')}</p>}
        {totpStatus === 'disabled' && <p className="status-success">{t('twoFADisabled')}</p>}
        {totpIsError && <p className="status-error">{totpErrMsg}</p>}

        {!totpSetup && !showDisable && (
          <div className="totp-actions">
            <button className="btn-secondary" onClick={handleSetup2FA}>
              <Smartphone size={15} /> {t('setup2FA')}
            </button>
            <button className="btn-ghost-danger" onClick={() => setShowDisable(true)}>
              {t('disable2FA')}
            </button>
          </div>
        )}

        {totpSetup && (
          <div className="totp-setup-card">
            <p className="totp-instructions">{t('twoFAScanQR')}</p>
            <img src={totpSetup.qr_code} alt="QR Code" className="totp-qr" />
            <p className="totp-secret-label">{t('twoFAManualCode')}</p>
            <code className="totp-secret">{totpSetup.secret}</code>
            <div className="form-field" style={{ marginTop: '1rem' }}>
              <label className="form-label">{t('twoFAEnterCode')}</label>
              <input className="form-input totp-verify-input" type="text" inputMode="numeric"
                maxLength={6} value={totpCode}
                onChange={e => setTotpCode(e.target.value.replace(/\D/g, ''))}
                placeholder="000000" />
            </div>
            <div className="modal-footer" style={{ padding: 0, marginTop: '0.75rem' }}>
              <button className="btn-secondary" onClick={() => setTotpSetup(null)}>{t('cancel')}</button>
              <button className="btn-primary" onClick={handleVerify2FA} disabled={totpCode.length !== 6}>
                {t('twoFAConfirm')}
              </button>
            </div>
          </div>
        )}

        {showDisable && (
          <div className="totp-setup-card">
            <p className="totp-instructions">{t('twoFADisableConfirm')}</p>
            <div className="form-field">
              <label className="form-label">{t('currentPassword')}</label>
              <input className="form-input" type="password" value={disablePw}
                onChange={e => setDisablePw(e.target.value)} autoFocus />
            </div>
            <div className="modal-footer" style={{ padding: 0, marginTop: '0.75rem' }}>
              <button className="btn-secondary" onClick={() => setShowDisable(false)}>{t('cancel')}</button>
              <button className="btn-danger" onClick={handleDisable2FA} disabled={!disablePw}>
                {t('disable2FA')}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="settings-logout-row">
        <button className="btn-logout" onClick={logout}><LogOut size={16} />{t('logout')}</button>
      </div>
    </div>
  );
}

/* ─── Users Section (Admin) ───────────────────────────────────────────────── */
function UsersSection() {
  const { user, t } = useApp();
  const [users, setUsers]         = useState([]);
  const [showAdd, setShowAdd]     = useState(false);
  const [resetUser, setResetUser] = useState(null);
  const [loading, setLoading]     = useState(true);

  const load = () => {
    setLoading(true);
    fetchUsers().then(setUsers).catch(console.error).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const handleDelete = async (uid, uname) => {
    if (!window.confirm(`${t('confirmDelete')} "${uname}"?`)) return;
    try { await deleteUser(uid); setUsers(prev => prev.filter(u => u.id !== uid)); }
    catch (e) { alert(e.message); }
  };

  return (
    <div className="settings-section">
      <div className="section-heading-row">
        <h3 className="section-heading">{t('userManagement')}</h3>
        <button className="btn-sm-primary" onClick={() => setShowAdd(true)}><Plus size={15} /> {t('addUser')}</button>
      </div>
      {loading ? <p className="loading-text">Loading…</p> : (
        <div className="user-list">
          {users.map(u => (
            <div key={u.id} className="user-row">
              <div className="user-row-avatar">{u.username[0].toUpperCase()}</div>
              <div className="user-row-info">
                <span className="user-row-name">{u.username}</span>
                <span className={`user-role-badge ${u.is_admin ? 'admin' : ''}`}>
                  {u.is_admin ? t('admin') : t('member')}
                </span>
              </div>
              <div className="user-row-actions">
                <button className="icon-btn" title={t('resetPassword')} onClick={() => setResetUser(u)}><KeyRound size={16} /></button>
                {u.id !== user.id && (
                  <button className="icon-btn danger" title={t('delete')} onClick={() => handleDelete(u.id, u.username)}><Trash2 size={16} /></button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {showAdd    && <AddUserModal t={t} onClose={() => setShowAdd(false)} onAdded={() => { setShowAdd(false); load(); }} />}
      {resetUser  && <ResetPasswordModal t={t} targetUser={resetUser} onClose={() => setResetUser(null)} />}
    </div>
  );
}

/* ─── Logs Section (Admin) ────────────────────────────────────────────────── */
function LogsSection() {
  const { t } = useApp();
  const [lines, setLines]         = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState('');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [source, setSource]       = useState('all');
  const bottomRef  = useRef(null);
  const intervalRef = useRef(null);

  const loadLogs = useCallback(async () => {
    try {
      const data = await fetchLogs(300, source);
      setLines(data.lines || []);
      setError('');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [source]);

  useEffect(() => { setLoading(true); loadLogs(); }, [loadLogs]);

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(loadLogs, 3000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [autoRefresh, loadLogs]);

  useEffect(() => {
    if (bottomRef.current) bottomRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [lines]);

  const getLineClass = (line) => {
    const l = line.toLowerCase();
    if (l.includes(' 4') || l.includes(' 5') || l.includes('error') || l.includes('failed') || l.includes('exception')) return 'log-line--error';
    if (l.includes('200') || l.includes('started') || l.includes('success')) return 'log-line--ok';
    if (l.includes('warn') || l.includes('warning') || l.includes('429')) return 'log-line--warn';
    return '';
  };

  return (
    <div className="settings-section">
      <div className="section-heading-row">
        <h3 className="section-heading">{t('adminLogs')}</h3>
        <div className="log-controls">
          <label className="checkbox-row" style={{ margin: 0 }}>
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
            <span style={{ fontSize: '0.85rem' }}>{t('autoRefresh')}</span>
          </label>
          <button className="icon-btn" title={t('refresh')} onClick={loadLogs}><RefreshCw size={16} /></button>
        </div>
      </div>

      {/* Source tabs */}
      <div className="log-source-tabs">
        {['all', 'uvicorn', 'supervisord'].map(s => (
          <button key={s} className={`log-tab ${source === s ? 'active' : ''}`} onClick={() => setSource(s)}>
            {s === 'all' ? 'All' : s === 'uvicorn' ? '⚙ API' : '🔧 System'}
          </button>
        ))}
      </div>

      {error && <p className="status-error">{error}</p>}
      <div className="log-viewer">
        {loading ? (
          <p className="log-loading">Loading logs…</p>
        ) : lines.length === 0 ? (
          <p className="log-loading">{t('noLogs')}</p>
        ) : (
          lines.map((line, i) => (
            <div key={i} className={`log-line ${getLineClass(line)}`}>{line}</div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

/* ─── Mail Section (Admin) ────────────────────────────────────────────────── */
function MailSection() {
  const { t } = useApp();
  const [cfg, setCfg]         = useState({ mail_host: '', mail_port: '587', mail_username: '', mail_password: '', mail_from: '', mail_tls: 'true', mail_enabled: 'false' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [testTo, setTestTo]   = useState('');
  const [testing, setTesting] = useState(false);
  const [status, setStatus]   = useState(null);

  useEffect(() => {
    fetchMailSettings()
      .then(data => setCfg(prev => ({ ...prev, ...data })))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true); setStatus(null);
    try {
      await saveMailSettings(cfg);
      setStatus('saved');
    } catch (e) { setStatus('error:' + e.message); }
    finally { setSaving(false); }
  };

  const handleTest = async () => {
    if (!testTo) return;
    setTesting(true); setStatus(null);
    try {
      await testMail(testTo);
      setStatus('test_ok');
    } catch (e) { setStatus('error:' + e.message); }
    finally { setTesting(false); }
  };

  const f = (key, val) => setCfg(prev => ({ ...prev, [key]: val }));

  if (loading) return <div className="settings-section"><p className="loading-text">Loading…</p></div>;

  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('adminMail')}</h3>
      <p className="settings-row-sub" style={{ marginBottom: '1.5rem' }}>{t('mailDesc')}</p>

      <div className="form-stack">
        <div className="form-row-two">
          <div className="form-field">
            <label className="form-label">{t('mailHost')}</label>
            <input className="form-input" value={cfg.mail_host} onChange={e => f('mail_host', e.target.value)} placeholder="smtp.gmail.com" />
          </div>
          <div className="form-field" style={{ maxWidth: 100 }}>
            <label className="form-label">{t('mailPort')}</label>
            <input className="form-input" type="number" value={cfg.mail_port} onChange={e => f('mail_port', e.target.value)} placeholder="587" />
          </div>
        </div>
        <div className="form-field">
          <label className="form-label">{t('mailUsername')}</label>
          <input className="form-input" value={cfg.mail_username} onChange={e => f('mail_username', e.target.value)} placeholder="you@gmail.com" autoComplete="off" />
        </div>
        <div className="form-field">
          <label className="form-label">{t('mailPassword')}</label>
          <input className="form-input" type="password" value={cfg.mail_password} onChange={e => f('mail_password', e.target.value)} autoComplete="new-password" />
        </div>
        <div className="form-field">
          <label className="form-label">{t('mailFrom')}</label>
          <input className="form-input" value={cfg.mail_from} onChange={e => f('mail_from', e.target.value)} placeholder="Knitting Library <you@gmail.com>" />
        </div>
        <div className="settings-row" style={{ padding: '0.5rem 0' }}>
          <div className="settings-row-info">
            <p className="settings-row-label">{t('mailTLS')}</p>
            <p className="settings-row-sub">{t('mailTLSSub')}</p>
          </div>
          <button className={`theme-toggle ${cfg.mail_tls === 'true' ? 'dark' : ''}`}
            onClick={() => f('mail_tls', cfg.mail_tls === 'true' ? 'false' : 'true')}>
            <span className="theme-toggle-knob" />
          </button>
        </div>

        {status === 'saved'   && <p className="status-success">{t('saved')}</p>}
        {status === 'test_ok' && <p className="status-success">{t('mailTestOk')}</p>}
        {status?.startsWith('error:') && <p className="status-error">{status.slice(6)}</p>}

        <button className="btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? t('saving') : t('saveSettings')}
        </button>

        <div className="mail-test-row">
          <input className="form-input" value={testTo} onChange={e => setTestTo(e.target.value)}
            placeholder={t('mailTestPlaceholder')} type="email" />
          <button className="btn-secondary" onClick={handleTest} disabled={testing || !testTo}>
            <Send size={15} /> {testing ? t('sending') : t('sendTestEmail')}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── 2FA Admin Section ───────────────────────────────────────────────────── */
function TwoFASection() {
  const { t } = useApp();
  const [users, setUsers]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(null);

  const load = () => {
    setLoading(true);
    fetch2FAStatus().then(setUsers).catch(console.error).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const handleReset = async (uid, uname) => {
    if (!window.confirm(`Reset 2FA for "${uname}"? They will need to set it up again.`)) return;
    setResetting(uid);
    try {
      await adminReset2FA(uid);
      load();
    } catch (e) { alert(e.message); }
    finally { setResetting(null); }
  };

  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('admin2FA')}</h3>
      <p className="settings-row-sub" style={{ marginBottom: '1.5rem' }}>{t('twoFAAdminDesc')}</p>
      {loading ? <p className="loading-text">Loading…</p> : (
        <div className="user-list">
          {users.map(u => (
            <div key={u.id} className="user-row">
              <div className="user-row-avatar">{u.username[0].toUpperCase()}</div>
              <div className="user-row-info">
                <span className="user-row-name">{u.username}</span>
                <span className={`user-role-badge ${u.totp_enabled ? 'admin' : ''}`}>
                  {u.totp_enabled
                    ? <><CheckCircle size={12} style={{ marginRight: 4 }} />{t('twoFAActive')}</>
                    : <><XCircle size={12} style={{ marginRight: 4 }} />{t('twoFANotSet')}</>
                  }
                </span>
              </div>
              <div className="user-row-actions">
                {u.totp_enabled && (
                  <button className="icon-btn danger" title={t('reset2FA')} disabled={resetting === u.id}
                    onClick={() => handleReset(u.id, u.username)}>
                    <KeyRound size={16} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Add User Modal ──────────────────────────────────────────────────────── */
function AddUserModal({ t, onClose, onAdded }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isAdmin, setIsAdmin]   = useState(false);
  const [error, setError]       = useState('');
  const [saving, setSaving]     = useState(false);

  const handleCreate = async () => {
    if (!username || !password) return;
    setSaving(true); setError('');
    try { await createUser({ username, password, is_admin: isAdmin }); onAdded(); }
    catch (e) { setError(e.message); setSaving(false); }
  };

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header"><h3>{t('addUser')}</h3><button className="modal-close" onClick={onClose}><X size={20} /></button></div>
        <div className="modal-body">
          <div className="form-field"><label className="form-label">{t('username')}</label><input className="form-input" value={username} onChange={e => setUsername(e.target.value)} autoFocus /></div>
          <div className="form-field"><label className="form-label">{t('password')}</label><input className="form-input" type="password" value={password} onChange={e => setPassword(e.target.value)} /></div>
          <label className="checkbox-row"><input type="checkbox" checked={isAdmin} onChange={e => setIsAdmin(e.target.checked)} /><span>{t('isAdmin')}</span></label>
          {error && <p className="status-error">{error}</p>}
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>{t('cancel')}</button>
          <button className="btn-primary" onClick={handleCreate} disabled={saving || !username || !password}>{saving ? t('saving') : t('createUser')}</button>
        </div>
      </div>
    </div>
  );
}

/* ─── Reset Password Modal ────────────────────────────────────────────────── */
function ResetPasswordModal({ t, targetUser, onClose }) {
  const [newPw, setNewPw] = useState('');
  const [done, setDone]   = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');

  const handleReset = async () => {
    if (newPw.length < 4) { setError(t('passwordTooShort')); return; }
    setSaving(true); setError('');
    try { await adminResetPassword(targetUser.id, newPw); setDone(true); }
    catch (e) { setError(e.message); setSaving(false); }
  };

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header"><h3>{t('resetPassword')}</h3><button className="modal-close" onClick={onClose}><X size={20} /></button></div>
        <div className="modal-body">
          {done ? <p className="status-success">{t('passwordChanged')}</p> : (
            <><p className="modal-hint">{t('newUserPassword')}: <strong>{targetUser.username}</strong></p>
              <div className="form-field"><label className="form-label">{t('newPassword')}</label><input className="form-input" type="password" value={newPw} onChange={e => setNewPw(e.target.value)} autoFocus /></div>
              {error && <p className="status-error">{error}</p>}</>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>{t('cancel')}</button>
          {!done && <button className="btn-primary" onClick={handleReset} disabled={saving || !newPw}>{saving ? t('saving') : t('savePassword')}</button>}
        </div>
      </div>
    </div>
  );
}

/* ─── Data Section ────────────────────────────────────────────────────────── */
function DataSection() {
  const { t } = useApp();
  const [exporting, setExporting] = useState(false);
  const [error, setError]         = useState('');

  const handleExport = async () => {
    setExporting(true); setError('');
    try { await exportLibrary(); }
    catch (e) { setError(e.message || 'Export failed'); }
    finally { setExporting(false); }
  };

  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('dataSection')}</h3>
      <div className="export-card">
        <div className="export-card-text">
          <p className="export-card-title">{t('exportTitle')}</p>
          <p className="export-card-desc">{t('exportDescription')}</p>
        </div>
        <button className="btn-export" onClick={handleExport} disabled={exporting}>
          <Download size={16} />
          {exporting ? t('exporting') : t('exportBtn')}
        </button>
        {error && <p className="form-error">{error}</p>}
      </div>
    </div>
  );
}
