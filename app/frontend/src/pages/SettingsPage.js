/**
 * SettingsPage.js
 * User settings: dark/light mode, language, change password.
 * Admin users also see a User Management section.
 */

import React, { useState, useEffect } from 'react';
import { Sun, Moon, Globe, Lock, Users, Plus, Trash2, KeyRound, X, ChevronLeft, Download, LogOut } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { changePassword, fetchUsers, createUser, deleteUser, adminResetPassword, exportLibrary } from '../utils/api';
import './SettingsPage.css';

export default function SettingsPage({ onBack }) {
  const { user, theme, language, t, updateSettings } = useApp();
  const [activeSection, setActiveSection] = useState('appearance');

  return (
    <div className="settings-page">
      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <div className="settings-topbar">
        <button className="settings-back" onClick={onBack}>
          <ChevronLeft size={20} />
          <span>{t('backToLibrary')}</span>
        </button>
        <h2 className="settings-title">{t('settings')}</h2>
        <div style={{ width: 80 }} />
      </div>

      <div className="settings-body">
        {/* ── Sidebar nav ─────────────────────────────────────────────── */}
        <nav className="settings-nav">
          <button
            className={`settings-nav-btn ${activeSection === 'appearance' ? 'active' : ''}`}
            onClick={() => setActiveSection('appearance')}
          >
            <Sun size={18} />
            {t('appearance')}
          </button>
          <button
            className={`settings-nav-btn ${activeSection === 'account' ? 'active' : ''}`}
            onClick={() => setActiveSection('account')}
          >
            <Lock size={18} />
            {t('account')}
          </button>
          {user?.is_admin && (
            <button
              className={`settings-nav-btn ${activeSection === 'users' ? 'active' : ''}`}
              onClick={() => setActiveSection('users')}
            >
              <Users size={18} />
              {t('userManagement')}
            </button>
          )}
          <button
            className={`settings-nav-btn ${activeSection === 'data' ? 'active' : ''}`}
            onClick={() => setActiveSection('data')}
          >
            <Download size={18} />
            {t('dataSection')}
          </button>
        </nav>

        {/* ── Content ─────────────────────────────────────────────────── */}
        <div className="settings-content">
          {activeSection === 'appearance' && <AppearanceSection />}
          {activeSection === 'account'    && <AccountSection />}
          {activeSection === 'users' && user?.is_admin && <UsersSection />}
          {activeSection === 'data'       && <DataSection />}
        </div>
      </div>
    </div>
  );
}

/* ─── Appearance Section ──────────────────────────────────────────────────── */

// Colour theme definitions — used to render the swatch previews
const COLOUR_THEMES = [
  {
    id: 'terracotta',
    labelKey: 'themeTerracotta',
    // light swatch colours
    bg:      '#f5f0e8',
    card:    '#ffffff',
    accent:  '#c4714a',
    // dark swatch colours
    bgDark:     '#1c1410',
    cardDark:   '#221810',
    accentDark: '#d4876a',
    // SVG flower path (simple 5-petal shape)
    flower: 'M8,4 C8,4 10,1 12,4 C15,4 15,7 12,8 C15,9 15,12 12,12 C10,15 8,15 8,12 C5,12 5,9 8,8 C5,7 5,4 8,4Z',
    flowerColour: '#c4714a',
    flowerColourDark: '#d4876a',
  },
  {
    id: 'rose',
    labelKey: 'themeRose',
    bg:      '#fdf5f6',
    card:    '#ffffff',
    accent:  '#c2637a',
    bgDark:     '#1e1216',
    cardDark:   '#241418',
    accentDark: '#e08898',
    flower: 'M10,3 C11,0 13,0 14,3 C17,2 18,4 16,6 C18,8 17,11 14,10 C13,13 11,13 10,10 C7,11 6,8 8,6 C6,4 7,2 10,3Z',
    flowerColour: '#c2637a',
    flowerColourDark: '#e08898',
  },
  {
    id: 'lavender',
    labelKey: 'themeLavender',
    bg:      '#f7f4fc',
    card:    '#ffffff',
    accent:  '#8b6cae',
    bgDark:     '#16121e',
    cardDark:   '#1c1626',
    accentDark: '#b094d4',
    flower: 'M10,2 C12,0 14,2 13,5 C16,4 17,7 15,9 C17,11 16,14 13,13 C12,16 10,16 9,13 C6,14 5,11 7,9 C5,7 6,4 9,5 C8,2 8,0 10,2Z',
    flowerColour: '#8b6cae',
    flowerColourDark: '#b094d4',
  },
  {
    id: 'sage',
    labelKey: 'themeSage',
    bg:      '#f4f7f3',
    card:    '#ffffff',
    accent:  '#5a8c6a',
    bgDark:     '#111a13',
    cardDark:   '#152018',
    accentDark: '#7aaa8a',
    flower: 'M9,3 C10,0 12,0 13,3 C16,3 17,5 15,7 C17,9 16,12 13,11 C12,14 10,14 9,11 C6,12 5,9 7,7 C5,5 6,3 9,3Z',
    flowerColour: '#5a8c6a',
    flowerColourDark: '#7aaa8a',
  },
  {
    id: 'berry',
    labelKey: 'themeBerry',
    bg:      '#fcf4fa',
    card:    '#ffffff',
    accent:  '#8e3a6e',
    bgDark:     '#1a1020',
    cardDark:   '#201226',
    accentDark: '#c874a8',
    flower: 'M10,2 C11,-1 13,0 14,3 C17,3 18,6 15,7 C17,10 16,13 13,12 C12,15 10,15 9,12 C6,13 5,10 7,7 C4,6 5,3 8,3 C9,0 9,-1 10,2Z',
    flowerColour: '#8e3a6e',
    flowerColourDark: '#c874a8',
  },
];

function ThemeSwatch({ themeData, isSelected, isDark, onClick }) {
  const bg     = isDark ? themeData.bgDark     : themeData.bg;
  const card   = isDark ? themeData.cardDark   : themeData.card;
  const accent = isDark ? themeData.accentDark : themeData.accent;
  const fc     = isDark ? themeData.flowerColourDark : themeData.flowerColour;

  return (
    <button
      className={`theme-swatch ${isSelected ? 'selected' : ''}`}
      onClick={onClick}
      aria-label={themeData.id}
      title={themeData.id}
    >
      {/* Mini app preview */}
      <div className="swatch-preview" style={{ background: bg }}>
        {/* Simulated header bar */}
        <div className="swatch-header" style={{ background: card, borderBottom: `1px solid ${accent}22` }}>
          <div className="swatch-dot" style={{ background: accent }} />
          <div className="swatch-line short" style={{ background: accent + '55' }} />
        </div>
        {/* Simulated grid cards */}
        <div className="swatch-grid">
          {[0,1,2,3].map(i => (
            <div key={i} className="swatch-card" style={{ background: card, boxShadow: `0 1px 4px ${accent}22` }}>
              {/* Little flower SVG on first card */}
              {i === 0 && (
                <svg viewBox="0 0 20 20" width="14" height="14" style={{ margin: '2px auto', display: 'block' }}>
                  <circle cx="10" cy="10" r="3" fill={fc} opacity="0.9" />
                  <circle cx="10" cy="4"  r="2.5" fill={fc} opacity="0.55" />
                  <circle cx="10" cy="16" r="2.5" fill={fc} opacity="0.55" />
                  <circle cx="4"  cy="10" r="2.5" fill={fc} opacity="0.55" />
                  <circle cx="16" cy="10" r="2.5" fill={fc} opacity="0.55" />
                  <circle cx="5"  cy="5"  r="2"   fill={fc} opacity="0.35" />
                  <circle cx="15" cy="5"  r="2"   fill={fc} opacity="0.35" />
                  <circle cx="5"  cy="15" r="2"   fill={fc} opacity="0.35" />
                  <circle cx="15" cy="15" r="2"   fill={fc} opacity="0.35" />
                </svg>
              )}
              <div className="swatch-line" style={{ background: accent + '33', marginTop: i === 0 ? 2 : 6 }} />
              <div className="swatch-line short" style={{ background: accent + '22' }} />
            </div>
          ))}
        </div>
        {/* Accent bar at bottom */}
        <div className="swatch-accent-bar" style={{ background: accent }} />
      </div>
      {/* Selection ring */}
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

      {/* ── Colour Theme picker ─────────────────────────────────────────── */}
      <div className="settings-row settings-row--column">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('colourTheme')}</p>
          <p className="settings-row-sub">{t('colourThemeSub')}</p>
        </div>
        <div className="theme-swatch-grid">
          {COLOUR_THEMES.map(ct => (
            <div key={ct.id} className="theme-swatch-wrap">
              <ThemeSwatch
                themeData={ct}
                isSelected={colourTheme === ct.id}
                isDark={theme === 'dark'}
                onClick={() => updateSettings(theme, language, currency, ct.id)}
              />
              <span className="swatch-label">{t(ct.labelKey)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Dark / Light mode toggle ────────────────────────────────────── */}
      <div className="settings-row">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('darkMode')}</p>
          <p className="settings-row-sub">
            {theme === 'dark' ? t('darkMode') : t('lightMode')}
          </p>
        </div>
        <button
          className={`theme-toggle ${theme === 'dark' ? 'dark' : ''}`}
          onClick={() => updateSettings(theme === 'dark' ? 'light' : 'dark', language, currency, colourTheme)}
          aria-label="Toggle theme"
        >
          <span className="theme-toggle-knob">
            {theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}
          </span>
        </button>
      </div>

      {/* ── Language ────────────────────────────────────────────────────── */}
      <div className="settings-row">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('language')}</p>
        </div>
        <div className="lang-switcher">
          <button
            className={`lang-btn ${language === 'en' ? 'active' : ''}`}
            onClick={() => updateSettings(theme, 'en', currency, colourTheme)}
          >
            🇬🇧 English
          </button>
          <button
            className={`lang-btn ${language === 'no' ? 'active' : ''}`}
            onClick={() => updateSettings(theme, 'no', currency, colourTheme)}
          >
            🇳🇴 Norsk
          </button>
        </div>
      </div>

      {/* ── Currency ────────────────────────────────────────────────────── */}
      <div className="settings-row">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('currency')}</p>
          <p className="settings-row-sub">{t('currencySub')}</p>
        </div>
        <div className="lang-switcher">
          {[
            { code: 'NOK', label: 'kr' },
            { code: 'USD', label: '$'  },
            { code: 'GBP', label: '£'  },
          ].map(c => (
            <button
              key={c.code}
              className={`lang-btn ${currency === c.code ? 'active' : ''}`}
              onClick={() => updateSettings(theme, language, c.code, colourTheme)}
            >
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
  const [status, setStatus]     = useState(null); // 'success' | 'error:message'
  const [saving, setSaving]     = useState(false);

  const handleSubmit = async () => {
    if (!oldPw || !newPw || !confirmPw) return;
    if (newPw !== confirmPw) { setStatus('error:' + t('passwordMismatch')); return; }
    if (newPw.length < 4)   { setStatus('error:' + t('passwordTooShort')); return; }
    setSaving(true);
    setStatus(null);
    try {
      await changePassword(oldPw, newPw);
      setStatus('success');
      setOldPw(''); setNewPw(''); setConfirmPw('');
    } catch (e) {
      setStatus('error:' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const isError   = status?.startsWith('error:');
  const errorMsg  = isError ? status.slice(6) : '';

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
          <input type="password" className="form-input" value={oldPw}
            onChange={e => setOldPw(e.target.value)} autoComplete="current-password" />
        </div>
        <div className="form-field">
          <label className="form-label">{t('newPassword')}</label>
          <input type="password" className="form-input" value={newPw}
            onChange={e => setNewPw(e.target.value)} autoComplete="new-password" />
        </div>
        <div className="form-field">
          <label className="form-label">{t('confirmNewPassword')}</label>
          <input type="password" className="form-input" value={confirmPw}
            onChange={e => setConfirmPw(e.target.value)} autoComplete="new-password" />
        </div>

        {status === 'success' && (
          <p className="status-success">{t('passwordChanged')}</p>
        )}
        {isError && <p className="status-error">{errorMsg}</p>}

        <button className="btn-primary" onClick={handleSubmit} disabled={saving || !oldPw || !newPw || !confirmPw}>
          {saving ? t('saving') : t('savePassword')}
        </button>
      </div>

      <div className="settings-logout-row">
        <button className="btn-logout" onClick={logout}>
          <LogOut size={16} />
          {t('logout')}
        </button>
      </div>
    </div>
  );
}

/* ─── Users Section (Admin only) ─────────────────────────────────────────── */
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
    try {
      await deleteUser(uid);
      setUsers(prev => prev.filter(u => u.id !== uid));
    } catch (e) { alert(e.message); }
  };

  return (
    <div className="settings-section">
      <div className="section-heading-row">
        <h3 className="section-heading">{t('userManagement')}</h3>
        <button className="btn-sm-primary" onClick={() => setShowAdd(true)}>
          <Plus size={15} /> {t('addUser')}
        </button>
      </div>

      {loading ? (
        <p className="loading-text">Loading…</p>
      ) : (
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
                <button className="icon-btn" title={t('resetPassword')}
                  onClick={() => setResetUser(u)}>
                  <KeyRound size={16} />
                </button>
                {u.id !== user.id && (
                  <button className="icon-btn danger" title={t('delete')}
                    onClick={() => handleDelete(u.id, u.username)}>
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showAdd && (
        <AddUserModal
          t={t}
          onClose={() => setShowAdd(false)}
          onAdded={() => { setShowAdd(false); load(); }}
        />
      )}

      {resetUser && (
        <ResetPasswordModal
          t={t}
          targetUser={resetUser}
          onClose={() => setResetUser(null)}
        />
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
    try {
      await createUser({ username, password, is_admin: isAdmin });
      onAdded();
    } catch (e) { setError(e.message); setSaving(false); }
  };

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{t('addUser')}</h3>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">{t('username')}</label>
            <input className="form-input" value={username} onChange={e => setUsername(e.target.value)} autoFocus />
          </div>
          <div className="form-field">
            <label className="form-label">{t('password')}</label>
            <input className="form-input" type="password" value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          <label className="checkbox-row">
            <input type="checkbox" checked={isAdmin} onChange={e => setIsAdmin(e.target.checked)} />
            <span>{t('isAdmin')}</span>
          </label>
          {error && <p className="status-error">{error}</p>}
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>{t('cancel')}</button>
          <button className="btn-primary" onClick={handleCreate} disabled={saving || !username || !password}>
            {saving ? t('saving') : t('createUser')}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Reset Password Modal ────────────────────────────────────────────────── */
function ResetPasswordModal({ t, targetUser, onClose }) {
  const [newPw, setNewPw]   = useState('');
  const [done, setDone]     = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');

  const handleReset = async () => {
    if (newPw.length < 4) { setError(t('passwordTooShort')); return; }
    setSaving(true); setError('');
    try {
      await adminResetPassword(targetUser.id, newPw);
      setDone(true);
    } catch (e) { setError(e.message); setSaving(false); }
  };

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{t('resetPassword')}</h3>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>
        <div className="modal-body">
          {done ? (
            <p className="status-success">{t('passwordChanged')}</p>
          ) : (
            <>
              <p className="modal-hint">{t('newUserPassword')}: <strong>{targetUser.username}</strong></p>
              <div className="form-field">
                <label className="form-label">{t('newPassword')}</label>
                <input className="form-input" type="password" value={newPw}
                  onChange={e => setNewPw(e.target.value)} autoFocus />
              </div>
              {error && <p className="status-error">{error}</p>}
            </>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>{done ? t('cancel') : t('cancel')}</button>
          {!done && (
            <button className="btn-primary" onClick={handleReset} disabled={saving || !newPw}>
              {saving ? t('saving') : t('savePassword')}
            </button>
          )}
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
    setExporting(true);
    setError('');
    try {
      await exportLibrary();
    } catch (e) {
      setError(e.message || 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('dataSection')}</h3>

      <div className="export-card">
        <div className="export-card-text">
          <p className="export-card-title">{t('exportTitle')}</p>
          <p className="export-card-desc">{t('exportDescription')}</p>
        </div>
        <button
          className="btn-export"
          onClick={handleExport}
          disabled={exporting}
        >
          <Download size={16} />
          {exporting ? t('exporting') : t('exportBtn')}
        </button>
        {error && <p className="form-error">{error}</p>}
      </div>
    </div>
  );
}
