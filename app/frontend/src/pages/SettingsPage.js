/**
 * SettingsPage.js
 * User settings: dark/light mode, language, change password.
 * Admin users also see a User Management section.
 */

import React, { useState, useEffect } from 'react';
import { Sun, Moon, Globe, Lock, Users, Plus, Trash2, KeyRound, X, ChevronLeft, Download } from 'lucide-react';
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
function AppearanceSection() {
  const { theme, language, t, updateSettings } = useApp();

  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('appearance')}</h3>

      {/* Theme */}
      <div className="settings-row">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('darkMode')}</p>
          <p className="settings-row-sub">
            {theme === 'dark' ? t('darkMode') : t('lightMode')}
          </p>
        </div>
        <button
          className={`theme-toggle ${theme === 'dark' ? 'dark' : ''}`}
          onClick={() => updateSettings(theme === 'dark' ? 'light' : 'dark', language)}
          aria-label="Toggle theme"
        >
          <span className="theme-toggle-knob">
            {theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}
          </span>
        </button>
      </div>

      {/* Language */}
      <div className="settings-row">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('language')}</p>
        </div>
        <div className="lang-switcher">
          <button
            className={`lang-btn ${language === 'en' ? 'active' : ''}`}
            onClick={() => updateSettings(theme, 'en')}
          >
            🇬🇧 English
          </button>
          <button
            className={`lang-btn ${language === 'no' ? 'active' : ''}`}
            onClick={() => updateSettings(theme, 'no')}
          >
            🇳🇴 Norsk
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Account Section ─────────────────────────────────────────────────────── */
function AccountSection() {
  const { user, t } = useApp();
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
