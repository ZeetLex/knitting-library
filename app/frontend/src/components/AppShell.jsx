import React, { useEffect, useRef, useState } from 'react';
import {
  BarChart2, BookOpen, Boxes, ChevronDown, ChevronRight, ChevronUp,
  CircleHelp, Home, Import, Menu, PackagePlus, Plus, Settings, Wrench, X,
} from 'lucide-react';
import { useApp } from '../utils/AppContext';
import './AppShell.css';

function BrandMark({ compact = false }) {
  return (
    <div className={`app-brand ${compact ? 'app-brand--compact' : ''}`}>
      <img className="app-brand-logo" src="/brand-logo.png" alt="" aria-hidden="true" />
      <div className="app-brand-text">
        <span className="app-brand-main">Knitting</span>
        <span className="app-brand-sub">Library</span>
      </div>
    </div>
  );
}

function AddActionMenu({ open, variant, onClose, onAddRecipe, onImportFolder, onAddYarn, onAddTool }) {
  const { t } = useApp();
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (event) => {
      if (ref.current && !ref.current.contains(event.target)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  const actions = [
    { icon: <BookOpen size={18} />, label: t('addRecipe'), sub: t('pdfOrImages'), onClick: onAddRecipe },
    { icon: <Import size={18} />, label: t('importFolder'), sub: t('workThroughFolder'), onClick: onImportFolder },
    { icon: <PackagePlus size={18} />, label: t('addYarn'), sub: t('navAddYarnHint'), onClick: onAddYarn },
    { icon: <Wrench size={18} />, label: t('addToolToInventory'), sub: t('navAddToolHint'), onClick: onAddTool },
  ];

  return (
    <div className={`add-menu add-menu--${variant}`} ref={ref}>
      <div className="add-menu-header">
        <span>{t('navAddSomething')}</span>
        <button onClick={onClose} aria-label={t('cancel')}><X size={16} /></button>
      </div>
      {actions.map(action => (
        <button
          key={action.label}
          className="add-menu-item"
          onClick={() => {
            onClose();
            action.onClick();
          }}
        >
          <span className="add-menu-icon">{action.icon}</span>
          <span className="add-menu-copy">
            <span className="add-menu-label">{action.label}</span>
            <span className="add-menu-sub">{action.sub}</span>
          </span>
          <ChevronRight size={16} />
        </button>
      ))}
    </div>
  );
}

function AppMenu({ open, onClose, onNavigate }) {
  const { t, logout } = useApp();

  if (!open) return null;

  const items = [
    { key: 'stats', icon: <BarChart2 size={18} />, label: t('statistics') },
    { key: 'help', icon: <CircleHelp size={18} />, label: t('helpTooltip') },
    { key: 'settings', icon: <Settings size={18} />, label: t('settings') },
  ];

  return (
    <div className="app-menu-overlay" onClick={onClose}>
      <aside className="app-menu" onClick={e => e.stopPropagation()}>
        <div className="app-menu-top">
          <BrandMark />
          <button className="app-menu-close" onClick={onClose} aria-label={t('cancel')}>
            <X size={20} />
          </button>
        </div>
        <div className="app-menu-items">
          {items.map(item => (
            <button
              key={item.key}
              className="app-menu-item"
              onClick={() => {
                onClose();
                onNavigate(item.key);
              }}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
        <button className="app-menu-logout" onClick={logout}>{t('logout')}</button>
      </aside>
    </div>
  );
}

function MobileNav({
  activeView,
  collapsed,
  onToggleCollapsed,
  onNavigate,
  onAddClick,
  onInventoryClick,
  onMenuClick,
}) {
  const { t } = useApp();
  const isHome = activeView === 'home';

  const items = [
    { key: 'home', icon: <Home size={21} />, label: t('navHome') },
    { key: 'recipes', icon: <BookOpen size={21} />, label: t('tabRecipes') },
    { key: 'inventory', icon: <Boxes size={21} />, label: t('tabInventory') },
  ];

  if (collapsed) {
    return (
      <button
        className="mobile-nav-peek"
        onClick={onToggleCollapsed}
        aria-label={t('navShowNavigation')}
      >
        <ChevronUp size={24} />
      </button>
    );
  }

  return (
    <nav className={`mobile-nav ${isHome ? 'mobile-nav--home' : 'mobile-nav--compact'}`} aria-label="Primary">
      <button
        className="mobile-nav-collapse"
        onClick={onToggleCollapsed}
        aria-label={t('navHideNavigation')}
      >
        <ChevronDown size={18} />
      </button>
      <button
        className={`mobile-nav-item-main ${activeView === 'home' ? 'active' : ''}`}
        onClick={() => onNavigate('home')}
        aria-label={t('navHome')}
      >
        <Home size={21} />
        <span>{t('navHome')}</span>
      </button>
      <button
        className={`mobile-nav-item-main ${activeView === 'recipes' ? 'active' : ''}`}
        onClick={() => onNavigate('recipes')}
        aria-label={t('tabRecipes')}
      >
        <BookOpen size={21} />
        <span>{t('tabRecipes')}</span>
      </button>
      <button className="mobile-nav-add" onClick={onAddClick} aria-label={t('navAddSomething')}>
        <Plus size={24} />
        <span>{t('navAdd')}</span>
      </button>
      <button
        className={`mobile-nav-item-main ${activeView === 'inventory' || activeView === 'yarnDatabase' ? 'active' : ''}`}
        onClick={() => onNavigate('inventory')}
        aria-label={t('tabInventory')}
      >
        {items[2].icon}
        <span>{items[2].label}</span>
      </button>
      <button className="mobile-nav-item-main" onClick={onMenuClick} aria-label={t('navMenu')}>
        <Menu size={21} />
        <span>{t('navMenu')}</span>
      </button>
    </nav>
  );
}

function DesktopSidebar({ activeView, onNavigate, onAddClick, onInventoryClick }) {
  const { t } = useApp();
  const primary = [
    { key: 'home', icon: <Home size={19} />, label: t('navHome') },
    { key: 'recipes', icon: <BookOpen size={19} />, label: t('tabRecipes') },
    { key: 'inventory', icon: <Boxes size={19} />, label: t('tabInventory') },
  ];
  const secondary = [
    { key: 'stats', icon: <BarChart2 size={18} />, label: t('statistics') },
    { key: 'help', icon: <CircleHelp size={18} />, label: t('helpTooltip') },
    { key: 'settings', icon: <Settings size={18} />, label: t('settings') },
  ];

  return (
    <aside className="desktop-sidebar">
      <button className="desktop-brand-button" onClick={() => onNavigate('home')}>
        <BrandMark />
      </button>
      <button className="desktop-add-btn" onClick={onAddClick}>
        <Plus size={18} />
        <span>{t('navAddSomething')}</span>
      </button>
      <div className="desktop-nav-group">
        {primary.map(item => (
          <button
            key={item.key}
            className={`desktop-nav-item ${
              activeView === item.key || (item.key === 'inventory' && activeView === 'yarnDatabase') ? 'active' : ''
            }`}
            onClick={() => onNavigate(item.key)}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </div>
      <div className="desktop-nav-group desktop-nav-group--secondary">
        {secondary.map(item => (
          <button
            key={item.key}
            className={`desktop-nav-item ${activeView === item.key ? 'active' : ''}`}
            onClick={() => onNavigate(item.key)}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}

export default function AppShell({
  activeView,
  onNavigate,
  onAddRecipe,
  onImportFolder,
  onAddYarn,
  onAddTool,
  children,
}) {
  const [addOpen, setAddOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileNavCollapsed, setMobileNavCollapsed] = useState(false);
  const isHome = activeView === 'home';

  useEffect(() => {
    const openMenu = () => setMenuOpen(true);
    window.addEventListener('knitting-open-app-menu', openMenu);
    return () => window.removeEventListener('knitting-open-app-menu', openMenu);
  }, []);

  const collapseMobileNav = () => {
    setAddOpen(false);
    setMenuOpen(false);
    setMobileNavCollapsed(true);
  };

  return (
    <div className={`app-shell ${isHome ? 'app-shell--home' : 'app-shell--compact'} ${mobileNavCollapsed ? 'app-shell--nav-collapsed' : ''}`}>
      <DesktopSidebar
        activeView={activeView}
        onNavigate={onNavigate}
        onAddClick={() => setAddOpen(o => !o)}
        onInventoryClick={() => onNavigate('inventory')}
      />
      <main className="app-content">
        {children}
      </main>
      <MobileNav
        activeView={activeView}
        collapsed={mobileNavCollapsed}
        onToggleCollapsed={mobileNavCollapsed ? () => setMobileNavCollapsed(false) : collapseMobileNav}
        onNavigate={onNavigate}
        onAddClick={() => setAddOpen(o => !o)}
        onInventoryClick={() => onNavigate('inventory')}
        onMenuClick={() => setMenuOpen(true)}
      />
      <AddActionMenu
        open={addOpen}
        variant="responsive"
        onClose={() => setAddOpen(false)}
        onAddRecipe={onAddRecipe}
        onImportFolder={onImportFolder}
        onAddYarn={onAddYarn}
        onAddTool={onAddTool}
      />
      <AppMenu open={menuOpen} onClose={() => setMenuOpen(false)} onNavigate={onNavigate} />
    </div>
  );
}
