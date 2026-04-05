import React, { useState, useRef, useEffect } from 'react';
import { Plus, Settings, BarChart2, ChevronDown, FolderDown, FileUp, Menu, X } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import './Header.css';

export default function Header({
  activeTab, onTabChange,
  onUploadClick, onBulkImportClick, onLogoClick, onSettingsClick,
  onStatsClick,
  addLabel, importCount,
  // Sub-tab props — only used when activeTab === 'yarns'
  yarnSubTab, onYarnSubTabChange,
}) {
  const { t, language } = useApp();
  const appSub = language === 'no' ? 'Bibliotek' : 'Library';
  const showSubTabs = activeTab === 'yarns';
  const [dropOpen, setDropOpen] = useState(false);
  const dropRef = useRef(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const mobileMenuRef = useRef(null);

  // Close split dropdown when clicking outside
  useEffect(() => {
    if (!dropOpen) return;
    const handler = (e) => { if (dropRef.current && !dropRef.current.contains(e.target)) setDropOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [dropOpen]);

  // Close mobile menu when clicking outside
  useEffect(() => {
    if (!mobileMenuOpen) return;
    const handler = (e) => {
      if (mobileMenuRef.current && !mobileMenuRef.current.contains(e.target)) setMobileMenuOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [mobileMenuOpen]);

  const handleMobileNav = (tab, yarnSub) => {
    setMobileMenuOpen(false);
    onTabChange(tab);
    if (yarnSub && onYarnSubTabChange) onYarnSubTabChange(yarnSub);
  };

  const isRecipes = activeTab === 'recipes';

  return (
    <header className={`header ${showSubTabs ? 'header--with-subtabs' : ''}`} ref={mobileMenuRef}>
      {/* ── Main row ── */}
      <div className="header-inner">
        <button className="header-logo" onClick={onLogoClick} aria-label={t('headerGoToLibrary')}>
          <span className="header-logo-icon">🧶</span>
          <span className="header-logo-text">
            <span className="header-logo-main">{language === 'no' ? 'Strikke' : 'Knitting'}</span>
            <span className="header-logo-sub">{appSub}</span>
          </span>
        </button>

        {/* Desktop tabs — hidden on mobile */}
        <nav className="header-tabs" aria-label="Main sections">
          <button
            className={`header-tab ${activeTab === 'recipes' ? 'active' : ''}`}
            onClick={() => onTabChange('recipes')}
          >
            {t('tabRecipes')}
          </button>
          <button
            className={`header-tab ${activeTab === 'yarns' ? 'active' : ''}`}
            onClick={() => onTabChange('yarns')}
          >
            {t('tabYarns')}
          </button>
        </nav>

        <div className="header-right">
          {/* Mobile hamburger — only visible on small screens */}
          <button
            className="header-mobile-menu-btn"
            onClick={() => setMobileMenuOpen(o => !o)}
            aria-label="Navigation menu"
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>

          {addLabel && (
            isRecipes ? (
              /* ── Split button: left = single upload, right = dropdown ── */
              <div className="header-split-btn" ref={dropRef}>
                <button className="header-split-main" onClick={onUploadClick} title={t('addRecipe')}>
                  <Plus size={18} />
                  <span>{addLabel}</span>
                </button>
                <button
                  className={`header-split-chevron ${importCount > 0 ? 'has-pending' : ''}`}
                  onClick={() => setDropOpen(o => !o)}
                  title={t('headerMoreOptions')}
                  aria-label={t('headerAddRecipeOptions')}
                >
                  <ChevronDown size={14} />
                  {importCount > 0 && <span className="split-badge">{importCount}</span>}
                </button>

                {dropOpen && (
                  <div className="header-split-dropdown">
                    <button className="split-drop-item" onClick={() => { setDropOpen(false); onUploadClick(); }}>
                      <FileUp size={15} />
                      <span>{t('addRecipe')}</span>
                      <span className="split-drop-hint">{t('pdfOrImages')}</span>
                    </button>
                    <button className="split-drop-item" onClick={() => { setDropOpen(false); onBulkImportClick(); }}>
                      <FolderDown size={15} />
                      <span>{t('importFolder')}</span>
                      {importCount > 0 && <span className="split-drop-badge">{importCount} {t('importPending')}</span>}
                      <span className="split-drop-hint">{t('workThroughFolder')}</span>
                    </button>
                  </div>
                )}
              </div>
            ) : (
              /* ── Plain button for Yarn Database ── */
              <button className="header-upload-btn" onClick={onUploadClick}>
                <Plus size={18} />
                <span>{addLabel}</span>
              </button>
            )
          )}
          {/* Settings + Stats — desktop only, available in hamburger on mobile */}
          <button className="header-icon-btn" onClick={onSettingsClick} title={t('settings')} aria-label={t('settings')}>
            <Settings size={20} />
          </button>
          <button className="header-icon-btn" onClick={onStatsClick} title={t('statistics')} aria-label={t('statistics')}>
            <BarChart2 size={20} />
          </button>
        </div>
      </div>

      {/* ── Mobile nav dropdown — full width, outside header-inner ── */}
      {mobileMenuOpen && (
        <div className="header-mobile-dropdown">
          <button
            className={`mobile-nav-item ${activeTab === 'recipes' ? 'active' : ''}`}
            onClick={() => handleMobileNav('recipes', null)}
          >
            <span className="mobile-nav-icon">📖</span>
            <span>{t('tabRecipes')}</span>
          </button>
          <button
            className={`mobile-nav-item ${activeTab === 'yarns' && yarnSubTab === 'inventory' ? 'active' : ''}`}
            onClick={() => handleMobileNav('yarns', 'inventory')}
          >
            <span className="mobile-nav-icon">🧶</span>
            <span>{t('tabInventory')}</span>
          </button>
          <button
            className={`mobile-nav-item ${activeTab === 'yarns' && yarnSubTab === 'yarndatabase' ? 'active' : ''}`}
            onClick={() => handleMobileNav('yarns', 'yarndatabase')}
          >
            <span className="mobile-nav-icon">🗂️</span>
            <span>{t('tabYarnDatabase')}</span>
          </button>
          <div className="mobile-nav-divider" />
          <button className="mobile-nav-item" onClick={() => { setMobileMenuOpen(false); onStatsClick(); }}>
            <span className="mobile-nav-icon"><BarChart2 size={18} /></span>
            <span>{t('statistics')}</span>
          </button>
          <button className="mobile-nav-item" onClick={() => { setMobileMenuOpen(false); onSettingsClick(); }}>
            <span className="mobile-nav-icon"><Settings size={18} /></span>
            <span>{t('settings')}</span>
          </button>
        </div>
      )}

      {/* ── Sub-tab row — shown only on Inventory tab ── */}
      {showSubTabs && (
        <div className="header-subtabs">
          <button
            className={`header-subtab ${yarnSubTab === 'inventory' ? 'active' : ''}`}
            onClick={() => onYarnSubTabChange('inventory')}
          >
            {t('tabInventory')}
          </button>
          <button
            className={`header-subtab ${yarnSubTab === 'yarndatabase' ? 'active' : ''}`}
            onClick={() => onYarnSubTabChange('yarndatabase')}
          >
            {t('tabYarnDatabase')}
          </button>
        </div>
      )}
    </header>
  );
}
