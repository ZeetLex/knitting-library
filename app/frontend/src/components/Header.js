import React from 'react';
import { Plus, Settings, LogOut } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import './Header.css';

export default function Header({ onUploadClick, onLogoClick, onSettingsClick }) {
  const { logout, t, language } = useApp();

  const appName = language === 'no' ? 'Strikkebibliotek' : 'Knitting Library';
  const appSub  = language === 'no' ? 'Bibliotek' : 'Library';

  return (
    <header className="header">
      <div className="header-inner">
        <button className="header-logo" onClick={onLogoClick} aria-label="Go to library">
          <span className="header-logo-icon">🧶</span>
          <span className="header-logo-text">
            <span className="header-logo-main">{language === 'no' ? 'Strikke' : 'Knitting'}</span>
            <span className="header-logo-sub">{appSub}</span>
          </span>
        </button>
        <div className="header-right">
          <button className="header-upload-btn" onClick={onUploadClick}>
            <Plus size={18} />
            <span>{t('addRecipe')}</span>
          </button>
          <button className="header-icon-btn" onClick={onSettingsClick} title={t('settings')} aria-label={t('settings')}>
            <Settings size={20} />
          </button>
          <button className="header-icon-btn" onClick={logout} title={t('logout')} aria-label={t('logout')}>
            <LogOut size={20} />
          </button>
        </div>
      </div>
    </header>
  );
}
