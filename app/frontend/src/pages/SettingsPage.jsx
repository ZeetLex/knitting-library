/**
 * SettingsPage.js
 * User settings (appearance, account, data) + admin panel (users, logs, mail, 2FA).
 * Admin sections are only rendered when user.is_admin === true.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Sun, Moon, Globe, Lock, Users, Plus, Trash2, KeyRound, X,
  ChevronLeft, ChevronRight, Download, LogOut, Terminal, Mail, ShieldCheck,
  RefreshCw, Send, CheckCircle, XCircle, Smartphone, Megaphone,
  Pencil, AtSign, Palette, Bot,
} from 'lucide-react';
import { CURRENCIES, useApp } from '../utils/AppContext';
import { LANGUAGE_OPTIONS } from '../utils/translations';
import {
  changePassword, fetchUsers, createUser, deleteUser, adminResetPassword, exportLibrary,
  fetchLogs, fetchMailSettings, saveMailSettings, testMail, testMailTemplate,
  fetch2FAStatus, adminReset2FA, setup2FA, verify2FASetup, disable2FA,
  createAnnouncement, listAnnouncements,
  updateUserEmail, sendWelcomeMail, fetchAISettings, saveAISettings, fetchAIModels, testAISettings,
} from '../utils/api';
import './SettingsPage.css';

export default function SettingsPage({ onBack }) {
  const { user, t } = useApp();
  const [activeSection, setActiveSection] = useState('appearance');
  const [mobileSectionOpen, setMobileSectionOpen] = useState(false);

  const navItems = [
    { id: 'appearance', icon: <Sun size={18} />,        label: t('appearance'), sub: t('settingsAppearanceSub') },
    { id: 'account',    icon: <Lock size={18} />,       label: t('account'), sub: t('settingsAccountSub') },
    { id: 'data',       icon: <Download size={18} />,   label: t('dataSection'), sub: t('settingsDataSub') },
    ...(user?.is_admin ? [
      { id: 'users',         icon: <Users size={18} />,       label: t('userManagement'), sub: t('settingsUsersSub'), adminDivider: true },
      { id: 'logs',          icon: <Terminal size={18} />,    label: t('adminLogs'), sub: t('settingsLogsSub') },
      { id: 'mail',          icon: <Mail size={18} />,        label: t('adminMail'), sub: t('settingsMailSub') },
      { id: 'ai',            icon: <Bot size={18} />,         label: t('adminAI'), sub: t('settingsAISub') },
      { id: 'twofa',         icon: <ShieldCheck size={18} />, label: t('admin2FA'), sub: t('settingsTwoFASub') },
      { id: 'announcements', icon: <Megaphone size={18} />,   label: t('updateNotes'), sub: t('settingsAnnouncementsSub') },
    ] : []),
  ];
  const activeItem = navItems.find(item => item.id === activeSection);
  const openSection = (id) => {
    setActiveSection(id);
    setMobileSectionOpen(true);
  };
  const handleTopBack = () => {
    if (mobileSectionOpen) {
      setMobileSectionOpen(false);
      return;
    }
    onBack();
  };

  return (
    <div className={`settings-page ${mobileSectionOpen ? 'settings-page--section-open' : ''}`}>
      <div className="settings-topbar">
        <button className="settings-back" onClick={handleTopBack}>
          <ChevronLeft size={20} />
          <span>{mobileSectionOpen ? t('settings') : t('backToLibrary')}</span>
        </button>
        <h2 className="settings-title">{mobileSectionOpen ? activeItem?.label : t('settings')}</h2>
        <div style={{ width: 80 }} />
      </div>

      <div className="settings-body">
        <div className="settings-mobile-index">
          {navItems.map((item) => (
            <React.Fragment key={item.id}>
              {item.adminDivider && (
                <div className="settings-mobile-divider">{t('adminPanel')}</div>
              )}
              <button className="settings-mobile-row" onClick={() => openSection(item.id)}>
                <span className="settings-mobile-row-icon">{item.icon}</span>
                <span className="settings-mobile-row-copy">
                  <span>{item.label}</span>
                  <small>{item.sub}</small>
                </span>
                <ChevronRight size={18} />
              </button>
            </React.Fragment>
          ))}
        </div>

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
                <span>{item.label}</span>
              </button>
            </React.Fragment>
          ))}
        </nav>

        <div className="settings-content">
          {activeSection === 'appearance' && <AppearanceSection />}
          {activeSection === 'account'    && <AccountSection />}
          {activeSection === 'data'       && <DataSection />}
          {user?.is_admin && activeSection === 'users'         && <UsersSection />}
          {user?.is_admin && activeSection === 'logs'          && <LogsSection />}
          {user?.is_admin && activeSection === 'mail'          && <MailSection />}
          {user?.is_admin && activeSection === 'ai'            && <AISection />}
          {user?.is_admin && activeSection === 'twofa'         && <TwoFASection />}
          {user?.is_admin && activeSection === 'announcements' && <AnnouncementsSection />}
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
  { id: 'ocean',      labelKey: 'themeOcean',      bg: '#e8f5f5', card: '#ffffff', accent: '#2d6a6a', bgDark: '#0e2a2a', cardDark: '#0e1f1f', accentDark: '#6eb0b0', flowerColour: '#2d6a6a', flowerColourDark: '#6eb0b0' },
  { id: 'willow',     labelKey: 'themeWillow',     bg: '#f4f6f0', card: '#ffffff', accent: '#6b7a4a', bgDark: '#11160e', cardDark: '#121910', accentDark: '#96a868', flowerColour: '#6b7a4a', flowerColourDark: '#96a868' },
];

const BACKGROUNDS = [
  { id: 'floral', labelKey: 'backgroundFloral', subKey: 'backgroundFloralSub' },
  { id: 'plain-white', labelKey: 'backgroundPlainWhite', subKey: 'backgroundPlainWhiteSub' },
  { id: 'cotton', labelKey: 'backgroundCotton', subKey: 'backgroundCottonSub' },
  { id: 'soft-paper', labelKey: 'backgroundSoftPaper', subKey: 'backgroundSoftPaperSub' },
  { id: 'warm-linen', labelKey: 'backgroundWarmLinen', subKey: 'backgroundWarmLinenSub' },
];

function normalizeBackgroundId(id) {
  return id === 'default' || id === 'floral-light' || id === 'floral-dark' ? 'floral' : id;
}

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

function BackgroundSwatch({ backgroundData, isSelected, onClick }) {
  const { t } = useApp();
  return (
    <button
      className={`background-swatch background-swatch--${backgroundData.id} ${isSelected ? 'selected' : ''}`}
      onClick={onClick}
      aria-label={t(backgroundData.labelKey)}
    >
      <span className="background-swatch-preview" />
      <span className="background-swatch-copy">
        <strong>{t(backgroundData.labelKey)}</strong>
        <small>{t(backgroundData.subKey)}</small>
      </span>
      {isSelected && <span className="background-swatch-check"><CheckCircle size={18} /></span>}
    </button>
  );
}

function AppearancePickerHeader({ title, onBack }) {
  const { t } = useApp();
  return (
    <div className="appearance-picker-header">
      <button className="appearance-picker-back" onClick={onBack}>
        <ChevronLeft size={18} />
        <span>{t('appearance')}</span>
      </button>
      <h4>{title}</h4>
    </div>
  );
}

function AppearanceSection() {
  const { theme, colourTheme, background, language, currency, t, updateSettings } = useApp();
  const [mobilePicker, setMobilePicker] = useState(null);
  const normalizedBackground = normalizeBackgroundId(background);
  const selectedTheme = COLOUR_THEMES.find(ct => ct.id === colourTheme) || COLOUR_THEMES[0];
  const selectedBackground = BACKGROUNDS.find(bg => bg.id === normalizedBackground) || BACKGROUNDS[0];
  const saveTheme = (nextColourTheme) => updateSettings(theme, language, currency, nextColourTheme, background);
  const saveBackground = (nextBackground) => updateSettings(theme, language, currency, colourTheme, nextBackground);

  if (mobilePicker === 'themes') {
    return (
      <div className="settings-section appearance-picker-page">
        <AppearancePickerHeader title={t('colourTheme')} onBack={() => setMobilePicker(null)} />
        <div className="theme-swatch-grid theme-swatch-grid--picker">
          {COLOUR_THEMES.map(ct => (
            <div key={ct.id} className="theme-swatch-wrap">
              <ThemeSwatch
                themeData={ct}
                isSelected={colourTheme === ct.id}
                isDark={theme === 'dark'}
                onClick={() => saveTheme(ct.id)}
              />
              <span className="swatch-label">{t(ct.labelKey)}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (mobilePicker === 'backgrounds') {
    return (
      <div className="settings-section appearance-picker-page">
        <AppearancePickerHeader title={t('backgroundSection')} onBack={() => setMobilePicker(null)} />
        <div className="background-swatch-grid">
          {BACKGROUNDS.map(bg => (
            <BackgroundSwatch
              key={bg.id}
              backgroundData={bg}
              isSelected={normalizedBackground === bg.id}
              onClick={() => saveBackground(bg.id)}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('appearance')}</h3>

      <div className="appearance-mobile-options">
        <button className="appearance-option-row" onClick={() => setMobilePicker('themes')}>
          <span className="appearance-option-icon"><Palette size={19} /></span>
          <span className="appearance-option-copy">
            <span>{t('colourTheme')}</span>
            <small>{t(selectedTheme.labelKey)}</small>
          </span>
          <ChevronRight size={18} />
        </button>
        <button className="appearance-option-row" onClick={() => setMobilePicker('backgrounds')}>
          <span className={`appearance-background-mini background-swatch--${selectedBackground.id}`} />
          <span className="appearance-option-copy">
            <span>{t('backgroundSection')}</span>
            <small>{t(selectedBackground.labelKey)}</small>
          </span>
          <ChevronRight size={18} />
        </button>
      </div>

      <div className="settings-row settings-row--column appearance-desktop-options">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('colourTheme')}</p>
          <p className="settings-row-sub">{t('colourThemeSub')}</p>
        </div>
        <div className="theme-swatch-grid">
          {COLOUR_THEMES.map(ct => (
            <div key={ct.id} className="theme-swatch-wrap">
              <ThemeSwatch themeData={ct} isSelected={colourTheme === ct.id} isDark={theme === 'dark'}
                onClick={() => saveTheme(ct.id)} />
              <span className="swatch-label">{t(ct.labelKey)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="settings-row settings-row--column appearance-desktop-options">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('backgroundSection')}</p>
          <p className="settings-row-sub">{t('backgroundSectionSub')}</p>
        </div>
        <div className="background-swatch-grid">
          {BACKGROUNDS.map(bg => (
            <BackgroundSwatch
              key={bg.id}
              backgroundData={bg}
              isSelected={normalizedBackground === bg.id}
              onClick={() => saveBackground(bg.id)}
            />
          ))}
        </div>
      </div>

      <div className="settings-row">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('darkMode')}</p>
          <p className="settings-row-sub">{theme === 'dark' ? t('darkMode') : t('lightMode')}</p>
        </div>
        <button className={`theme-toggle ${theme === 'dark' ? 'dark' : ''}`}
          onClick={() => updateSettings(theme === 'dark' ? 'light' : 'dark', language, currency, colourTheme, background)}>
          <span className="theme-toggle-knob">{theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}</span>
        </button>
      </div>
      <div className="settings-row">
        <div className="settings-row-info"><p className="settings-row-label">{t('language')}</p></div>
        <div className="lang-switcher">
          {LANGUAGE_OPTIONS.map(option => (
            <button
              key={option.code}
              className={`lang-btn ${language === option.code ? 'active' : ''}`}
              onClick={() => updateSettings(theme, option.code, currency, colourTheme, background)}
            >
              {option.flag} {option.nativeName}
            </button>
          ))}
        </div>
      </div>
      <div className="settings-row">
        <div className="settings-row-info">
          <p className="settings-row-label">{t('currency')}</p>
          <p className="settings-row-sub">{t('currencySub')}</p>
        </div>
        <div className="lang-switcher">
          {CURRENCIES.map(c => (
            <button key={c.code} className={`lang-btn ${currency === c.code ? 'active' : ''}`}
              onClick={() => updateSettings(theme, language, c.code, colourTheme, background)}>
              {c.label.split(' — ')[0]} {c.code}
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
  const [editEmailUser, setEditEmailUser] = useState(null);
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
                {u.email ? (
                  <span className="user-row-email">{u.email}</span>
                ) : (
                  <button className="user-row-add-email" onClick={() => setEditEmailUser(u)}>
                    <AtSign size={11} /> add email
                  </button>
                )}
              </div>
              <div className="user-row-actions">
                {u.email && (
                  <button className="icon-btn" title="Edit email" onClick={() => setEditEmailUser(u)}><AtSign size={16} /></button>
                )}
                <button className="icon-btn" title={t('resetPassword')} onClick={() => setResetUser(u)}><KeyRound size={16} /></button>
                {u.id !== user.id && (
                  <button className="icon-btn danger" title={t('delete')} onClick={() => handleDelete(u.id, u.username)}><Trash2 size={16} /></button>
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
      {resetUser    && <ResetPasswordModal t={t} targetUser={resetUser} onClose={() => setResetUser(null)} />}
      {editEmailUser && (
        <EditEmailModal
          t={t}
          targetUser={editEmailUser}
          onClose={() => setEditEmailUser(null)}
          onSaved={(uid, email) => {
            setUsers(prev => prev.map(u => u.id === uid ? { ...u, email } : u));
            setEditEmailUser(null);
          }}
        />
      )}
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
    if (l.includes('auth_fail') || l.includes(' 4') || l.includes(' 5') || l.includes('error') || l.includes('failed') || l.includes('exception')) return 'log-line--error';
    if (l.includes('auth_ok') || l.includes('200') || l.includes('started') || l.includes('success')) return 'log-line--ok';
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
        {['all', 'uvicorn', 'supervisord', 'auth', 'ai'].map(s => (
          <button key={s} className={`log-tab ${source === s ? 'active' : ''}`} onClick={() => setSource(s)}>
            {s === 'all' ? 'All' : s === 'uvicorn' ? '⚙ API' : s === 'supervisord' ? '🔧 System' : s === 'auth' ? '🔐 Auth' : '✨ AI'}
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

/* ─── Mail default templates (mirrors backend _DEFAULT_* constants) ──────── */
const defaultForgotSubject = (t) => t('defaultForgotSubject');
const defaultForgotBody = (t) => t('defaultForgotBody');
const defaultWelcomeSubject = (t) => t('defaultWelcomeSubject');
const defaultWelcomeBody = (t) => t('defaultWelcomeBody');

/* ─── Mail Section (Admin) ────────────────────────────────────────────────── */
function MailSection() {
  const { t } = useApp();
  const [cfg, setCfg]         = useState({ mail_host: '', mail_port: '587', mail_username: '', mail_password: '', mail_from: '', mail_tls: 'true', mail_enabled: 'false', mail_announcements_enabled: 'false', mail_tmpl_forgot_subject: '', mail_tmpl_forgot_body: '', mail_tmpl_welcome_subject: '', mail_tmpl_welcome_body: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [testTo, setTestTo]   = useState('');
  const [testing, setTesting] = useState(false);
  const [status, setStatus]   = useState(null);
  const [templateModal, setTemplateModal] = useState(null); // null | 'forgot' | 'welcome'

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

  const handleTemplateSave = (subjectKey, bodyKey, subject, body) => {
    setCfg(prev => ({ ...prev, [subjectKey]: subject, [bodyKey]: body }));
    setTemplateModal(null);
    // Save to backend immediately
    saveMailSettings({ ...cfg, [subjectKey]: subject, [bodyKey]: body }).catch(console.error);
  };

  if (loading) return <div className="settings-section"><p className="loading-text">Loading…</p></div>;

  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('adminMail')}</h3>
      <p className="settings-row-sub" style={{ marginBottom: '1.5rem' }}>{t('mailDesc')}</p>

      <div className="form-stack">
        <div className="settings-row" style={{ padding: '0.5rem 0', marginBottom: '0.25rem' }}>
          <div className="settings-row-info">
            <p className="settings-row-label">{t('mailEnable')}</p>
            <p className="settings-row-sub">{t('mailEnableSub')}</p>
          </div>
          <button className={`theme-toggle ${cfg.mail_enabled === 'true' ? 'dark' : ''}`}
            onClick={() => f('mail_enabled', cfg.mail_enabled === 'true' ? 'false' : 'true')}>
            <span className="theme-toggle-knob" />
          </button>
        </div>

        <div className="settings-divider" style={{ margin: '0.25rem 0 0.75rem' }} />

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

        {/* ── Email Templates ── */}
        <div className="settings-divider" />
        <h4 className="section-subheading">{t('emailTemplates')}</h4>

        <div className="settings-row">
          <div className="settings-row-info">
            <p className="settings-row-label">{t('forgotPasswordEmail')}</p>
            <p className="settings-row-sub">{t('forgotPasswordEmailSub')} <code>{'{USERNAME}'}</code> {t('and')} <code>{'{PASSWORD}'}</code>.</p>
          </div>
          <button className="btn-secondary btn-icon-label" onClick={() => setTemplateModal('forgot')}>
            <Pencil size={14} /> {t('edit')}
          </button>
        </div>

        <div className="settings-row">
          <div className="settings-row-info">
            <p className="settings-row-label">{t('welcomeEmail')}</p>
            <p className="settings-row-sub">{t('welcomeEmailSub')} <code>{'{USERNAME}'}</code> {t('and')} <code>{'{PASSWORD}'}</code>.</p>
          </div>
          <button className="btn-secondary btn-icon-label" onClick={() => setTemplateModal('welcome')}>
            <Pencil size={14} /> {t('edit')}
          </button>
        </div>

        {/* ── Announcement emails ── */}
        <div className="settings-divider" />
        <h4 className="section-subheading">{t('notifications')}</h4>

        <div className="settings-row">
          <div className="settings-row-info">
            <p className="settings-row-label">{t('emailUpdateNotes')}</p>
            <p className="settings-row-sub">{t('emailUpdateNotesSub')}</p>
          </div>
          <button
            className={`theme-toggle ${cfg.mail_announcements_enabled === 'true' ? 'dark' : ''}`}
            onClick={() => f('mail_announcements_enabled', cfg.mail_announcements_enabled === 'true' ? 'false' : 'true')}
          >
            <span className="theme-toggle-knob" />
          </button>
        </div>
      </div>

      {templateModal === 'forgot' && (
        <TemplateEditorModal
          t={t}
          title={t('forgotPasswordEmail')}
          subjectKey="mail_tmpl_forgot_subject"
          bodyKey="mail_tmpl_forgot_body"
          subject={cfg.mail_tmpl_forgot_subject || defaultForgotSubject(t)}
          body={cfg.mail_tmpl_forgot_body || defaultForgotBody(t)}
          requiredTokens={['{USERNAME}', '{PASSWORD}']}
          availableTokens={['{USERNAME}', '{PASSWORD}']}
          onClose={() => setTemplateModal(null)}
          onSave={handleTemplateSave}
        />
      )}
      {templateModal === 'welcome' && (
        <TemplateEditorModal
          t={t}
          title={t('welcomeEmail')}
          subjectKey="mail_tmpl_welcome_subject"
          bodyKey="mail_tmpl_welcome_body"
          subject={cfg.mail_tmpl_welcome_subject || defaultWelcomeSubject(t)}
          body={cfg.mail_tmpl_welcome_body || defaultWelcomeBody(t)}
          requiredTokens={['{USERNAME}', '{PASSWORD}']}
          availableTokens={['{USERNAME}', '{PASSWORD}', '{APP_URL}']}
          onClose={() => setTemplateModal(null)}
          onSave={handleTemplateSave}
        />
      )}
    </div>
  );
}

/* ─── AI Text Recognition Section (Admin) ─────────────────────────────────── */
function AISection() {
  const { t, language } = useApp();
  const providerPresets = [
    {
      id: 'openai',
      title: t('aiPresetOpenAI'),
      description: t('aiPresetOpenAISub'),
      baseUrl: 'https://api.openai.com/v1',
      model: 'gpt-4o-mini',
    },
    {
      id: 'ollama',
      title: t('aiPresetOllama'),
      description: t('aiPresetOllamaSub'),
      baseUrl: 'http://host.docker.internal:11434/v1',
      model: '',
    },
    {
      id: 'lmstudio',
      title: t('aiPresetLMStudio'),
      description: t('aiPresetLMStudioSub'),
      baseUrl: 'http://host.docker.internal:1234/v1',
      model: '',
    },
  ];
  const [cfg, setCfg] = useState({
    ai_enabled: 'false',
    ai_provider: 'openai_compatible',
    ai_base_url: 'http://host.docker.internal:11434/v1',
    ai_model: '',
    ai_api_key: '',
    ai_timeout: '600',
    ai_max_pages: '8',
    ai_prompt_mode: 'default',
    ai_custom_prompt: '',
    ai_cleanup_enabled: 'false',
    ai_cleanup_custom_prompt: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [models, setModels] = useState([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelStatus, setModelStatus] = useState('');
  const [status, setStatus] = useState(null);

  useEffect(() => {
    fetchAISettings()
      .then(data => setCfg(prev => ({ ...prev, ...data })))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const f = (key, value) => setCfg(prev => ({ ...prev, [key]: value }));

  const applyProviderPreset = (preset) => {
    setCfg(prev => ({
      ...prev,
      ai_provider: 'openai_compatible',
      ai_base_url: preset.baseUrl,
      ai_model: preset.model || prev.ai_model,
    }));
    setModels([]);
    setModelStatus('');
  };

  const loadModels = useCallback(async (nextCfg) => {
    if (!nextCfg.ai_base_url) {
      setModels([]);
      return;
    }
    setModelsLoading(true);
    setModelStatus('');
    try {
      const result = await fetchAIModels(nextCfg);
      setModels(result.models || []);
      setModelStatus((result.models || []).length ? 'loaded' : 'empty');
    } catch (e) {
      setModels([]);
      setModelStatus('error:' + e.message);
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (loading || !cfg.ai_base_url) return;
    const timer = setTimeout(() => loadModels(cfg), 650);
    return () => clearTimeout(timer);
  }, [cfg.ai_base_url, cfg.ai_api_key, loading, loadModels]);

  const handleSave = async () => {
    setSaving(true); setStatus(null);
    try {
      await saveAISettings(cfg);
      setStatus('saved');
    } catch (e) { setStatus('error:' + e.message); }
    finally { setSaving(false); }
  };

  const handleTest = async () => {
    setTesting(true); setStatus(null);
    try {
      const result = await testAISettings(cfg);
      setStatus('test_ok:' + (result.response || 'OK'));
    } catch (e) { setStatus('error:' + e.message); }
    finally { setTesting(false); }
  };

  if (loading) return <div className="settings-section"><p className="loading-text">Loading…</p></div>;

  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('adminAI')}</h3>
      <p className="settings-row-sub ai-section-intro">{t('aiDesc')}</p>

      <div className="form-stack ai-settings-form">
        <div className="ai-settings-card ai-enable-card">
          <div className="settings-row-info">
            <p className="settings-row-label">{t('aiEnable')}</p>
            <p className="settings-row-sub">{t('aiEnableSub')}</p>
          </div>
          <button className={`theme-toggle ${cfg.ai_enabled === 'true' ? 'dark' : ''}`}
            onClick={() => f('ai_enabled', cfg.ai_enabled === 'true' ? 'false' : 'true')}>
            <span className="theme-toggle-knob" />
          </button>
        </div>

        <div className="ai-settings-card">
          <div className="ai-card-heading">
            <div>
              <h4>{t('recognitionMode')}</h4>
              <p>{t('recognitionModeSub')}</p>
            </div>
          </div>
          <div className="ai-provider-grid">
            <div className="ai-provider-card active" aria-current="true">
              <span>{t('recognitionAIVision')}</span>
              <small>{t('recognitionAIVisionSub')}</small>
            </div>
          </div>
        </div>

        <div className="ai-settings-card">
          <div className="ai-card-heading">
            <div>
              <h4>{t('aiConnection')}</h4>
              <p>{t('aiConnectionSub')}</p>
            </div>
          </div>

          <div className="ai-provider-grid">
            {providerPresets.map(preset => (
              <button
                key={preset.id}
                type="button"
                className={`ai-provider-card ${cfg.ai_base_url === preset.baseUrl ? 'active' : ''}`}
                onClick={() => applyProviderPreset(preset)}
              >
                <span>{preset.title}</span>
                <small>{preset.description}</small>
              </button>
            ))}
          </div>

          <div className="form-field">
            <label className="form-label">{t('aiProvider')}</label>
            <select className="form-input" value={cfg.ai_provider} onChange={e => f('ai_provider', e.target.value)}>
              <option value="openai_compatible">{t('aiProviderOpenAICompatible')}</option>
            </select>
          </div>

          <div className="form-field">
            <label className="form-label">{t('aiBaseUrl')}</label>
            <input className="form-input" value={cfg.ai_base_url} onChange={e => f('ai_base_url', e.target.value)} placeholder="https://api.openai.com/v1" />
            <p className="settings-row-sub ai-inline-help">{t('aiBaseUrlHint')}</p>
          </div>

          <div className="ai-model-grid">
            <div className="form-field">
              <label className="form-label">{t('aiModel')}</label>
              <div className="ai-model-row">
                {models.length > 0 ? (
                  <select className="form-input" value={cfg.ai_model} onChange={e => f('ai_model', e.target.value)}>
                    {!cfg.ai_model && <option value="">{t('selectModel')}</option>}
                    {cfg.ai_model && !models.includes(cfg.ai_model) && <option value={cfg.ai_model}>{cfg.ai_model}</option>}
                    {models.map(model => <option key={model} value={model}>{model}</option>)}
                  </select>
                ) : (
                  <input className="form-input" value={cfg.ai_model} onChange={e => f('ai_model', e.target.value)} placeholder="gpt-4o-mini, llava, qwen2.5-vl" />
                )}
                <button className="btn-secondary ai-model-refresh" onClick={() => loadModels(cfg)} disabled={modelsLoading || !cfg.ai_base_url} title={t('refreshModels')}>
                  <RefreshCw size={15} className={modelsLoading ? 'spin-icon' : ''} />
                </button>
              </div>
              {modelStatus === 'loaded' && <p className="settings-row-sub ai-inline-help">{t('modelsLoaded').replace('{COUNT}', String(models.length))}</p>}
              {modelStatus === 'empty' && <p className="settings-row-sub ai-inline-help">{t('noModelsFound')}</p>}
              {modelStatus?.startsWith('error:') && <p className="status-error ai-inline-help">{modelStatus.slice(6)}</p>}
            </div>
            <div className="form-field">
              <label className="form-label">{t('aiApiKey')}</label>
              <input className="form-input" type="password" value={cfg.ai_api_key} onChange={e => f('ai_api_key', e.target.value)} autoComplete="new-password" placeholder={t('optional')} />
              <p className="settings-row-sub ai-inline-help">{t('aiApiKeyHint')}</p>
            </div>
          </div>

          <div className="ai-number-grid">
            <div className="form-field">
              <label className="form-label">{t('aiTimeout')}</label>
              <input className="form-input" type="number" min="60" max="1800" value={cfg.ai_timeout} onChange={e => f('ai_timeout', e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-label">{t('aiMaxPages')}</label>
              <input className="form-input" type="number" min="1" max="30" value={cfg.ai_max_pages} onChange={e => f('ai_max_pages', e.target.value)} />
            </div>
          </div>
        </div>

        <div className="ai-settings-card">
          <div className="ai-card-heading ai-card-heading-row">
            <div>
              <h4>{t('aiPrompt')}</h4>
              <p>{t('aiPromptModeSub')}</p>
            </div>
            <div className="ai-segmented">
              <button className={cfg.ai_prompt_mode !== 'custom' ? 'active' : ''} onClick={() => f('ai_prompt_mode', 'default')}>{t('default')}</button>
              <button className={cfg.ai_prompt_mode === 'custom' ? 'active' : ''} onClick={() => f('ai_prompt_mode', 'custom')}>{t('custom')}</button>
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">{cfg.ai_prompt_mode === 'custom' ? t('aiCustomPrompt') : t('aiDefaultPromptPreview')}</label>
            <textarea
              className="form-input form-textarea ai-prompt-textarea"
              value={cfg.ai_prompt_mode === 'custom' ? cfg.ai_custom_prompt : t('defaultOcrPrompt')}
              onChange={e => f('ai_custom_prompt', e.target.value)}
              readOnly={cfg.ai_prompt_mode !== 'custom'}
              rows={7}
            />
            <p className="settings-row-sub ai-inline-help">
              {cfg.ai_prompt_mode === 'custom' ? t('aiCustomPromptHint') : t('aiDefaultPromptHint').replace('{LANGUAGE}', language)}
            </p>
          </div>
        </div>

        <div className="ai-settings-card">
          <div className="ai-card-heading ai-card-heading-row">
            <div>
              <h4>{t('aiCleanupWorkflow')}</h4>
              <p>{t('aiCleanupWorkflowSub')}</p>
            </div>
            <button className={`theme-toggle ${cfg.ai_cleanup_enabled === 'true' ? 'dark' : ''}`}
              onClick={() => f('ai_cleanup_enabled', cfg.ai_cleanup_enabled === 'true' ? 'false' : 'true')}>
              <span className="theme-toggle-knob" />
            </button>
          </div>
          <div className="form-field">
            <label className="form-label">{t('aiCleanupPrompt')}</label>
            <textarea
              className="form-input form-textarea ai-prompt-textarea"
              value={cfg.ai_cleanup_custom_prompt}
              onChange={e => f('ai_cleanup_custom_prompt', e.target.value)}
              placeholder={t('defaultAiCleanupPrompt')}
              rows={7}
            />
            <p className="settings-row-sub ai-inline-help">
              {t('aiCleanupPromptHint')}
            </p>
          </div>
        </div>

        {status === 'saved' && <p className="status-success">{t('saved')}</p>}
        {status?.startsWith('test_ok:') && <p className="status-success">{t('aiTestOk')} {status.slice(8)}</p>}
        {status?.startsWith('error:') && <p className="status-error">{status.slice(6)}</p>}

        <div className="mail-test-row">
          <button className="btn-primary" onClick={handleSave} disabled={saving}>{saving ? t('saving') : t('saveSettings')}</button>
          <button className="btn-secondary" onClick={handleTest} disabled={testing || !cfg.ai_base_url || !cfg.ai_model}>
            <Send size={15} /> {testing ? t('testing') : t('testConnection')}
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
    if (!window.confirm(t('reset2FAConfirm').replace('{USERNAME}', uname))) return;
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

/* ─── Announcements Section (Admin) ─────────────────────────────────────── */
function AnnouncementsSection() {
  const { t } = useApp();
  const [announcements, setAnnouncements] = useState([]);
  const [loading, setLoading]             = useState(true);
  const [showPush, setShowPush]           = useState(false);

  const load = () => {
    setLoading(true);
    listAnnouncements()
      .then(setAnnouncements)
      .catch(console.error)
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const formatDate = (iso) => {
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  };

  return (
    <div className="settings-section">
      <div className="section-heading-row">
        <h3 className="section-heading">{t('updateNotes')}</h3>
        <button className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}
          onClick={() => setShowPush(true)}>
          <Megaphone size={15} />
          {t('pushUpdateNotes')}
        </button>
      </div>
      <p className="settings-row-sub" style={{ marginBottom: '1.25rem' }}>
        {t('updateNotesSub')}
      </p>

      {loading ? (
        <p className="loading-text">Loading…</p>
      ) : announcements.length === 0 ? (
        <p className="settings-row-sub">{t('noAnnouncements')}</p>
      ) : (
        <div className="announcement-history">
          {announcements.map(a => (
            <div key={a.id} className="announcement-history-item">
              <div className="announcement-history-title">{a.title}</div>
              {a.body && <div className="announcement-history-body">{a.body}</div>}
              <div className="announcement-history-meta">
                {t('pushedBy')} <strong>{a.created_by}</strong> · {formatDate(a.created_at)}
              </div>
            </div>
          ))}
        </div>
      )}

      {showPush && (
        <PushAnnouncementModal
          t={t}
          onClose={() => setShowPush(false)}
          onPushed={() => { setShowPush(false); load(); }}
        />
      )}
    </div>
  );
}

/* ─── Push Announcement Modal ─────────────────────────────────────────────── */
function PushAnnouncementModal({ t, onClose, onPushed }) {
  const [title, setTitle]   = useState('');
  const [body, setBody]     = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');

  const handlePush = async () => {
    if (!title.trim()) { setError(t('titleRequired')); return; }
    setSaving(true); setError('');
    try {
      await createAnnouncement(title.trim(), body.trim());
      onPushed();
    } catch (e) {
      setError(e.message || t('announcementPushError'));
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="settings-modal announcement-push-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3><Megaphone size={18} style={{ marginRight: 8, verticalAlign: 'middle' }} />{t('pushUpdateNotes')}</h3>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">{t('title')}</label>
            <input
              className="form-input"
              placeholder={t('announcementTitlePlaceholder')}
              value={title}
              onChange={e => setTitle(e.target.value)}
              autoFocus
              maxLength={120}
            />
          </div>
          <div className="form-field">
            <label className="form-label">{t('updateNotes')}</label>
            <textarea
              className="form-input announcement-textarea"
              placeholder={t('announcementBodyPlaceholder')}
              value={body}
              onChange={e => setBody(e.target.value)}
              rows={7}
            />
          </div>
          {error && <p className="status-error">{error}</p>}
          <p className="modal-hint">
            {t('announcementModalHint')}
          </p>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose} disabled={saving}>{t('cancel')}</button>
          <button className="btn-primary" onClick={handlePush} disabled={saving || !title.trim()}>
            {saving ? t('pushing') : <><Send size={14} style={{ marginRight: 6 }} />{t('pushToAllUsers')}</>}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Add User Modal ──────────────────────────────────────────────────────── */
function AddUserModal({ t, onClose, onAdded }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail]       = useState('');
  const [isAdmin, setIsAdmin]   = useState(false);
  const [error, setError]       = useState('');
  const [saving, setSaving]     = useState(false);
  const [createdUser, setCreatedUser] = useState(null); // {id, username, email, password} after create

  const handleCreate = async () => {
    if (!username || !password) return;
    setSaving(true); setError('');
    try {
      const result = await createUser({ username, password, email, is_admin: isAdmin });
      if (email.trim()) {
        // Show welcome mail prompt before closing
        setCreatedUser({ ...result, password });
      } else {
        onAdded();
      }
    } catch (e) { setError(e.message); setSaving(false); }
  };

  if (createdUser) {
    return (
      <WelcomeMailModal
        t={t}
        user={createdUser}
        onDone={onAdded}
      />
    );
  }

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header"><h3>{t('addUser')}</h3><button className="modal-close" onClick={onClose}><X size={20} /></button></div>
        <div className="modal-body">
          <div className="form-field"><label className="form-label">{t('username')}</label><input className="form-input" value={username} onChange={e => setUsername(e.target.value)} autoFocus /></div>
          <div className="form-field"><label className="form-label">{t('password')}</label><input className="form-input" type="password" value={password} onChange={e => setPassword(e.target.value)} /></div>
          <div className="form-field">
            <label className="form-label">{t('email')} <span className="form-label-optional">({t('optional')})</span></label>
            <input className="form-input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="user@example.com" />
          </div>
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

/* ─── Welcome Mail Modal ──────────────────────────────────────────────────── */
function WelcomeMailModal({ t, user, onDone }) {
  const [sending, setSending] = useState(false);
  const [status, setStatus]   = useState(null); // 'ok' | 'error:...'

  const handleSend = async () => {
    setSending(true);
    try {
      await sendWelcomeMail(user.id, user.password);
      setStatus('ok');
    } catch (e) {
      setStatus('error:' + e.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile">
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{t('userCreated')}</h3>
        </div>
        <div className="modal-body">
          <p className="modal-hint">
            {t('userCreatedMessage').replace('{USERNAME}', user.username)}
            {user.email && <> {t('sendWelcomeEmailPrompt').replace('{EMAIL}', user.email)}</>}
          </p>
          {status === 'ok' && <p className="status-success">{t('welcomeEmailSent')}</p>}
          {status?.startsWith('error:') && <p className="status-error">{status.slice(6)}</p>}
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onDone}>{t('skip')}</button>
          {!status && (
            <button className="btn-primary" onClick={handleSend} disabled={sending}>
              <Mail size={14} style={{ marginRight: 6 }} />
              {sending ? t('sending') : t('sendWelcomeEmail')}
            </button>
          )}
          {status && <button className="btn-primary" onClick={onDone}>{t('done')}</button>}
        </div>
      </div>
    </div>
  );
}

/* ─── Edit Email Modal ────────────────────────────────────────────────────── */
function EditEmailModal({ t, targetUser, onClose, onSaved }) {
  const [email, setEmail]   = useState(targetUser.email || '');
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');

  const handleSave = async () => {
    setSaving(true); setError('');
    try {
      await updateUserEmail(targetUser.id, email.trim());
      onSaved(targetUser.id, email.trim());
    } catch (e) { setError(e.message); setSaving(false); }
  };

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{t('email')} — {targetUser.username}</h3>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">{t('emailAddress')} <span className="form-label-optional">({t('leaveBlankToRemove')})</span></label>
            <input className="form-input" type="email" value={email} onChange={e => setEmail(e.target.value)} autoFocus placeholder="user@example.com" />
          </div>
          {error && <p className="status-error">{error}</p>}
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>{t('cancel')}</button>
          <button className="btn-primary" onClick={handleSave} disabled={saving}>{saving ? t('saving') : t('saveEmail')}</button>
        </div>
      </div>
    </div>
  );
}

/* ─── Template Editor Modal ──────────────────────────────────────────────── */
function TemplateEditorModal({ t, title, subjectKey, bodyKey, subject, body, requiredTokens, availableTokens, onClose, onSave }) {
  const [subj, setSubj]     = useState(subject || '');
  const [bodyText, setBody] = useState(body || '');
  const [testTo, setTestTo] = useState('');
  const [testing, setTesting] = useState(false);
  const [testStatus, setTestStatus] = useState(null);
  const [error, setError]   = useState('');

  const validate = () => {
    for (const tok of requiredTokens) {
      if (!subj.includes(tok) && !bodyText.includes(tok)) {
        return t('requiredTokenMissing').replace('{TOKEN}', tok);
      }
    }
    return '';
  };

  const handleSave = () => {
    const err = validate();
    if (err) { setError(err); return; }
    onSave(subjectKey, bodyKey, subj, bodyText);
  };

  const handleTest = async () => {
    if (!testTo) return;
    setTesting(true); setTestStatus(null);
    try {
      await testMailTemplate(testTo, subj, bodyText);
      setTestStatus('ok');
    } catch (e) { setTestStatus('error:' + e.message); }
    finally { setTesting(false); }
  };

  const insertToken = (tok) => {
    setBody(prev => prev + tok);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="settings-modal settings-modal--wide" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">{t('emailSubject')}</label>
            <input className="form-input" value={subj} onChange={e => { setSubj(e.target.value); setError(''); }} placeholder={t('emailSubjectPlaceholder')} />
          </div>
          <div className="form-field" style={{ marginTop: '0.75rem' }}>
            <label className="form-label">{t('emailBody')}</label>
            <textarea
              className="form-input form-textarea"
              value={bodyText}
              onChange={e => { setBody(e.target.value); setError(''); }}
              rows={10}
              placeholder={t('emailBodyPlaceholder')}
            />
          </div>
          <div className="template-tokens">
            <span className="template-tokens-label">{t('insertToken')}</span>
            {availableTokens.map(tok => (
              <button key={tok} className={`token-chip ${requiredTokens.includes(tok) ? 'token-chip--required' : ''}`} onClick={() => insertToken(tok)} type="button">
                {tok}
              </button>
            ))}
            <span className="template-tokens-hint">{t('requiredTokensHint')}</span>
          </div>
          {error && <p className="status-error" style={{ marginTop: '0.5rem' }}>{error}</p>}

          <div className="settings-divider" style={{ margin: '1rem 0' }} />
          <p className="settings-row-sub" style={{ marginBottom: '0.5rem' }}>{t('templateTestHint')}</p>
          <div className="mail-test-row">
            <input className="form-input" value={testTo} onChange={e => setTestTo(e.target.value)} placeholder="test@example.com" type="email" />
            <button className="btn-secondary" onClick={handleTest} disabled={testing || !testTo}>
              <Send size={15} /> {testing ? t('sending') : t('sendTestEmail')}
            </button>
          </div>
          {testStatus === 'ok' && <p className="status-success" style={{ marginTop: '0.5rem' }}>{t('mailTestOk')}</p>}
          {testStatus?.startsWith('error:') && <p className="status-error" style={{ marginTop: '0.5rem' }}>{testStatus.slice(6)}</p>}
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>{t('cancel')}</button>
          <button className="btn-primary" onClick={handleSave}>{t('saveTemplate')}</button>
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
