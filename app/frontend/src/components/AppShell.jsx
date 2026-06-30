import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft, BarChart2, BookOpen, Boxes, ChevronDown, ChevronLeft, ChevronRight, ChevronUp,
  CheckCircle2, CircleHelp, Home, Images, Import, Menu, PackagePlus, Play, Plus, Settings, Wrench, X,
} from 'lucide-react';
import { useApp } from '../utils/AppContext';
import WorkQueueDock from './WorkQueueDock';
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

function AddActionMenu({ open, variant, onClose, onImportRecipe, onAddYarn, onAddTool }) {
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
    { icon: <Import size={18} />, label: t('importRecipe') || t('importWizardTitle'), sub: t('importRecipeHint') || t('workThroughFolder'), onClick: onImportRecipe },
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
  recipeMode,
  recipeProjectStatus,
  recipeHasImages,
  recipeImagesVisible,
  onToggleCollapsed,
  onNavigate,
  onAddClick,
  onInventoryClick,
  onMenuClick,
  onRecipeBack,
  onRecipeActions,
  onRecipeProjectAction,
  onRecipeImagesToggle,
}) {
  const { t } = useApp();
  const isHome = activeView === 'home';
  const projectStarted = recipeProjectStatus === 'active' || recipeProjectStatus === 'finished';

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

  if (recipeMode) {
    return (
      <nav className="mobile-nav mobile-nav--recipe" aria-label="Recipe">
        <button
          className="mobile-nav-collapse"
          onClick={onToggleCollapsed}
          aria-label={t('navHideNavigation')}
        >
          <ChevronDown size={18} />
        </button>
        <button
          className="mobile-nav-item-main"
          onClick={() => onNavigate('home')}
          aria-label={t('navHome')}
        >
          <Home size={21} />
          <span>{t('navHome')}</span>
        </button>
        <button
          className="mobile-nav-item-main active"
          onClick={onRecipeBack}
          aria-label={t('backToLibrary')}
        >
          <ArrowLeft size={21} />
          <span>{t('backToLibrary')}</span>
        </button>
        <button
          className={`mobile-nav-recipe-project ${projectStarted ? 'mobile-nav-recipe-project--status' : ''}`}
          onClick={onRecipeProjectAction}
          aria-label={projectStarted ? (t('status') || 'Status') : t('startProject')}
        >
          {projectStarted ? <CheckCircle2 size={21} /> : <Play size={21} />}
          <span>{projectStarted ? (t('status') || 'Status') : (t('start') || t('startProject'))}</span>
        </button>
        <button
          className={`mobile-nav-item-main ${recipeImagesVisible ? 'active' : ''}`}
          onClick={onRecipeImagesToggle}
          disabled={!recipeHasImages}
          aria-label={recipeImagesVisible ? (t('hideImages') || 'Hide images') : (t('showImages') || t('mobileTabImages') || 'Images')}
          aria-pressed={recipeImagesVisible}
        >
          <Images size={21} />
          <span>{t('mobileTabImages') || 'Images'}</span>
        </button>
        <button
          className="mobile-nav-item-main"
          onClick={onRecipeActions}
          aria-label={t('recipeActions') || 'Actions'}
        >
          <Wrench size={21} />
          <span>{t('recipeActions') || 'Actions'}</span>
        </button>
      </nav>
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

function DesktopSidebar({ activeView, collapsed, onToggleCollapsed, onNavigate, onAddClick, onInventoryClick, queue, onOpenImport, onOpenRecipe, onCancelAI, onDismissAI }) {
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
    <aside className={`desktop-sidebar ${collapsed ? 'desktop-sidebar--collapsed' : ''}`}>
      <div className="desktop-sidebar-top">
        <button className="desktop-brand-button" onClick={() => onNavigate('home')} title={collapsed ? 'Knitting Library' : undefined}>
          <BrandMark compact={collapsed} />
        </button>
        <button
          className="desktop-sidebar-toggle"
          onClick={onToggleCollapsed}
          title={collapsed ? t('navShowNavigation') : t('navHideNavigation')}
          aria-label={collapsed ? t('navShowNavigation') : t('navHideNavigation')}
          aria-pressed={collapsed}
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>
      <button className="desktop-add-btn" onClick={onAddClick} title={collapsed ? t('navAddSomething') : undefined}>
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
            title={collapsed ? item.label : undefined}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </div>
      {!collapsed && (
        <WorkQueueDock
          queue={queue}
          variant="desktop"
          onOpenImport={onOpenImport}
          onOpenRecipe={onOpenRecipe}
          onCancelAI={onCancelAI}
          onDismissAI={onDismissAI}
        />
      )}
      <div className="desktop-nav-group desktop-nav-group--secondary">
        {secondary.map(item => (
          <button
            key={item.key}
            className={`desktop-nav-item ${activeView === item.key ? 'active' : ''}`}
            onClick={() => onNavigate(item.key)}
            title={collapsed ? item.label : undefined}
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
  recipeMode = false,
  onNavigate,
  onAddRecipe,
  onImportFolder,
  onImportRecipe,
  onAddYarn,
  onAddTool,
  onRecipeBack,
  queue,
  onOpenImport,
  onOpenRecipe,
  onCancelAI,
  onDismissAI,
  children,
}) {
  const [addOpen, setAddOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileNavCollapsed, setMobileNavCollapsed] = useState(false);
  const [recipeMobileState, setRecipeMobileState] = useState({
    projectStatus: 'none',
    hasImages: false,
    imagesVisible: false,
  });
  const [desktopSidebarCollapsed, setDesktopSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem('knitting_desktop_sidebar_collapsed') === 'true';
    } catch (_) {
      return false;
    }
  });
  const isHome = activeView === 'home';

  const handleContentWheel = useCallback((event) => {
    if (window.matchMedia('(max-width: 899px)').matches) return;
    if (event.defaultPrevented || event.ctrlKey) return;

    const direction = Math.sign(event.deltaY);
    let node = event.target instanceof HTMLElement ? event.target : event.target?.parentElement;
    while (node && node !== event.currentTarget) {
      const style = window.getComputedStyle(node);
      const canScrollY = /(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 1;
      if (canScrollY) {
        const atTop = node.scrollTop <= 0;
        const atBottom = node.scrollTop + node.clientHeight >= node.scrollHeight - 1;
        if ((direction < 0 && !atTop) || (direction > 0 && !atBottom)) return;
      }
      node = node.parentElement;
    }

    const maxScroll = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) - window.innerHeight;
    if (maxScroll <= 0) return;
    const before = window.scrollY;
    window.scrollBy({ top: event.deltaY, left: event.deltaX, behavior: 'auto' });
    if (window.scrollY !== before) event.preventDefault();
  }, []);

  useEffect(() => {
    const openMenu = () => setMenuOpen(true);
    window.addEventListener('knitting-open-app-menu', openMenu);
    return () => window.removeEventListener('knitting-open-app-menu', openMenu);
  }, []);

  useEffect(() => {
    const updateRecipeMobileState = (event) => {
      setRecipeMobileState(state => ({ ...state, ...(event.detail || {}) }));
    };
    window.addEventListener('knitting-recipe-mobile-state', updateRecipeMobileState);
    return () => window.removeEventListener('knitting-recipe-mobile-state', updateRecipeMobileState);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('recipe-view-lock', recipeMode);
    document.body.classList.toggle('recipe-view-lock', recipeMode);

    return () => {
      document.documentElement.classList.remove('recipe-view-lock');
      document.body.classList.remove('recipe-view-lock');
    };
  }, [recipeMode]);

  const collapseMobileNav = () => {
    setAddOpen(false);
    setMenuOpen(false);
    setMobileNavCollapsed(true);
  };

  const toggleDesktopSidebar = () => {
    setDesktopSidebarCollapsed(collapsed => {
      const next = !collapsed;
      try { localStorage.setItem('knitting_desktop_sidebar_collapsed', String(next)); } catch (_) {}
      return next;
    });
  };

  return (
    <div className={`app-shell ${isHome ? 'app-shell--home' : 'app-shell--compact'} ${recipeMode ? 'app-shell--recipe' : ''} ${mobileNavCollapsed ? 'app-shell--nav-collapsed' : ''} ${desktopSidebarCollapsed ? 'app-shell--desktop-sidebar-collapsed' : ''}`}>
      <DesktopSidebar
        activeView={activeView}
        collapsed={desktopSidebarCollapsed}
        onToggleCollapsed={toggleDesktopSidebar}
        onNavigate={onNavigate}
        onAddClick={() => setAddOpen(o => !o)}
        onInventoryClick={() => onNavigate('inventory')}
        queue={queue}
        onOpenImport={onOpenImport}
        onOpenRecipe={onOpenRecipe}
        onCancelAI={onCancelAI}
        onDismissAI={onDismissAI}
      />
      <main className="app-content" onWheel={handleContentWheel}>
        {children}
      </main>
      <MobileNav
        activeView={activeView}
        collapsed={mobileNavCollapsed}
        recipeMode={recipeMode}
        recipeProjectStatus={recipeMobileState.projectStatus}
        recipeHasImages={recipeMobileState.hasImages}
        recipeImagesVisible={recipeMobileState.imagesVisible}
        onToggleCollapsed={mobileNavCollapsed ? () => setMobileNavCollapsed(false) : collapseMobileNav}
        onNavigate={onNavigate}
        onAddClick={() => setAddOpen(o => !o)}
        onInventoryClick={() => onNavigate('inventory')}
        onMenuClick={() => setMenuOpen(true)}
        onRecipeBack={onRecipeBack}
        onRecipeActions={() => window.dispatchEvent(new CustomEvent('knitting-recipe-mobile-panel', { detail: 'actions' }))}
        onRecipeProjectAction={() => window.dispatchEvent(new CustomEvent('knitting-recipe-project-action'))}
        onRecipeImagesToggle={() => window.dispatchEvent(new CustomEvent('knitting-recipe-toggle-images'))}
      />
      <AddActionMenu
        open={addOpen}
        variant="responsive"
        onClose={() => setAddOpen(false)}
        onImportRecipe={onImportRecipe || onImportFolder || onAddRecipe}
        onAddYarn={onAddYarn}
        onAddTool={onAddTool}
      />
      <AppMenu open={menuOpen} onClose={() => setMenuOpen(false)} onNavigate={onNavigate} />
    </div>
  );
}
