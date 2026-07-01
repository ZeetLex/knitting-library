import React, { useState, useCallback, useEffect, useRef } from 'react';
import { AppProvider, useApp } from './utils/AppContext';
import LoginPage from './pages/LoginPage';
import SetupPage from './pages/SetupPage';
import HomePage from './pages/HomePage';
import Library from './pages/Library';
import RecipeViewer from './pages/RecipeViewer';
import YarnLibrary from './pages/YarnLibrary';
import YarnViewer from './pages/YarnViewer';
import InventoryPage from './pages/InventoryPage';
import SettingsPage from './pages/SettingsPage';
import StatisticsPage from './pages/StatisticsPage';
import HelpPage from './pages/HelpPage';
import YarnUploadModal from './components/YarnUploadModal';
import ImportWizard from './components/ImportWizard';
import AppShell from './components/AppShell';
import AnnouncementModal from './components/AnnouncementModal';
import WorkQueueDock from './components/WorkQueueDock';
import { getImportQueue, fetchPendingAnnouncements, dismissAnnouncement, fetchWorkQueue, cancelAIJob, dismissAIJob, fetchNavigationProgress, saveNavigationProgress } from './utils/api';
import './App.css';

const APP_RESUME_PREFIX = 'knitting_app_resume_v1';

function appResumeKey(user) {
  return `${APP_RESUME_PREFIX}_${user?.id || user?.username || 'guest'}`;
}

function saveAppResume(user, data) {
  if (!user || !data?.activeView) return;
  try {
    localStorage.setItem(appResumeKey(user), JSON.stringify({ ...data, updatedAt: Date.now() }));
  } catch (_) {}
}

function readAppResume(user) {
  if (!user) return null;
  try {
    const raw = localStorage.getItem(appResumeKey(user));
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

function AppInner() {
  const { user, loading, setupRequired, t } = useApp();
  const [activeView, setActiveView]           = useState('home');
  const [viewingRecipeId, setViewingRecipeId] = useState(null);
  const [viewingYarnId, setViewingYarnId]     = useState(null);
  const [yarnUploadOpen, setYarnUploadOpen]   = useState(false);
  const [importOpen, setImportOpen]           = useState(false);
  const [importCount, setImportCount]         = useState(0);
  const [showSettings, setShowSettings]       = useState(false);
  const [showStats, setShowStats]             = useState(false);
  const [showHelp, setShowHelp]               = useState(false);
  const [refreshKey, setRefreshKey]           = useState(0);
  const [yarnRefreshKey, setYarnRefreshKey]   = useState(0);
  const [inventoryAddRequest, setInventoryAddRequest] = useState(null);
  const [inventoryRefreshKey, setInventoryRefreshKey] = useState(0);
  const [workQueue, setWorkQueue]         = useState(null);
  const [recipeInitialView, setRecipeInitialView] = useState('original');
  const resumeCheckedRef = useRef(false);

  const checkImport = useCallback(() => {
    getImportQueue().then(r => setImportCount(r.count || 0)).catch(() => {});
  }, []);

  const refreshWorkQueue = useCallback(() => {
    if (!user) return;
    fetchWorkQueue()
      .then(data => {
        setWorkQueue(data);
        setImportCount(data?.imports?.count || 0);
      })
      .catch(() => {});
  }, [user]);

  const persistAppLocation = useCallback((data) => {
    if (!user || !data?.activeView) return;
    const payload = {
      activeView: data.activeView,
      recipeId: data.recipeId || '',
      initialViewMode: data.initialViewMode || 'original',
      yarnId: data.yarnId || '',
    };
    saveAppResume(user, payload);
    saveNavigationProgress(payload).catch(() => {});
  }, [user]);

  // ── Announcements ─────────────────────────────────────────────────────────
  const [pendingAnnouncements, setPendingAnnouncements] = useState([]);

  const handleDismissAnnouncements = useCallback(async () => {
    // Dismiss all currently shown announcements at once
    for (const a of pendingAnnouncements) {
      await dismissAnnouncement(a.id).catch(() => {});
    }
    setPendingAnnouncements([]);
  }, [pendingAnnouncements]);

  // Only poll import queue once user is confirmed logged in.
  useEffect(() => { if (user) { checkImport(); refreshWorkQueue(); } }, [user, checkImport, refreshWorkQueue]);

  useEffect(() => {
    if (!user) {
      setWorkQueue(null);
      return undefined;
    }
    const timer = setInterval(refreshWorkQueue, 3000);
    return () => clearInterval(timer);
  }, [user, refreshWorkQueue]);

  // Fetch pending announcements once the user logs in
  useEffect(() => {
    if (user) {
      fetchPendingAnnouncements()
        .then(data => setPendingAnnouncements(data || []))
        .catch(() => {});
    } else {
      setPendingAnnouncements([]);
    }
  }, [user]);

  const handleNavigate = (view) => {
    setActiveView(view);
    setViewingRecipeId(null);
    setViewingYarnId(null);
    setRecipeInitialView('original');
    setShowStats(false);
    setShowSettings(false);
    setShowHelp(false);
    persistAppLocation({ activeView: view });
  };

  const navigateApp = (view) => {
    if (view === 'settings') {
      setShowSettings(true);
      setShowStats(false);
      setShowHelp(false);
      setViewingRecipeId(null);
      setViewingYarnId(null);
      persistAppLocation({ activeView: 'settings' });
      return;
    }
    if (view === 'stats') {
      setShowStats(true);
      setShowSettings(false);
      setShowHelp(false);
      setViewingRecipeId(null);
      setViewingYarnId(null);
      persistAppLocation({ activeView: 'stats' });
      return;
    }
    if (view === 'help') {
      setShowHelp(true);
      setShowSettings(false);
      setShowStats(false);
      setViewingRecipeId(null);
      setViewingYarnId(null);
      persistAppLocation({ activeView: 'help' });
      return;
    }
    handleNavigate(view);
  };

  const openRecipe = (id, initialView = 'original') => {
    setActiveView('recipes');
    setShowSettings(false);
    setShowStats(false);
    setShowHelp(false);
    setRecipeInitialView(initialView);
    setViewingRecipeId(id);
    persistAppLocation({ activeView: 'recipes', recipeId: id, initialViewMode: initialView });
  };

  const openYarn = (id) => {
    setActiveView('yarnDatabase');
    setViewingYarnId(id);
    persistAppLocation({ activeView: 'yarnDatabase', yarnId: id });
  };

  const handleImportRecipe = () => {
    setActiveView('recipes');
    setViewingRecipeId(null);
    setRecipeInitialView('original');
    setImportOpen(true);
    persistAppLocation({ activeView: 'recipes' });
  };

  const handleImportFolder = () => {
    handleImportRecipe();
  };

  const handleAddYarn = () => {
    setActiveView('inventory');
    setViewingYarnId(null);
    setYarnUploadOpen(true);
    persistAppLocation({ activeView: 'inventory' });
  };

  const handleAddTool = () => {
    setActiveView('inventory');
    setViewingRecipeId(null);
    setViewingYarnId(null);
    setShowSettings(false);
    setShowStats(false);
    setShowHelp(false);
    setInventoryAddRequest({ type: 'tool', nonce: Date.now() });
    persistAppLocation({ activeView: 'inventory' });
  };

  useEffect(() => {
    if (!user) {
      resumeCheckedRef.current = false;
      return;
    }
    if (resumeCheckedRef.current) return;
    resumeCheckedRef.current = true;
    let cancelled = false;
    const applySaved = (saved) => {
      if (!saved?.activeView || cancelled) return;
      setShowSettings(saved.activeView === 'settings');
      setShowStats(saved.activeView === 'stats');
      setShowHelp(saved.activeView === 'help');
      if (saved.activeView === 'settings' || saved.activeView === 'stats' || saved.activeView === 'help') {
        setViewingRecipeId(null);
        setViewingYarnId(null);
        return;
      }
      setActiveView(saved.activeView);
      setViewingRecipeId(saved.activeView === 'recipes' && saved.recipeId ? saved.recipeId : null);
      setViewingYarnId(saved.activeView === 'yarnDatabase' && saved.yarnId ? saved.yarnId : null);
      setRecipeInitialView(saved.initialViewMode || 'original');
    };
    fetchNavigationProgress()
      .then(saved => applySaved(saved?.exists ? saved : readAppResume(user)))
      .catch(() => applySaved(readAppResume(user)));
    return () => { cancelled = true; };
  }, [user]);

  if (loading) return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100vh', background:'var(--bg-primary)' }}>
      <div style={{ width:36, height:36, border:'3px solid var(--border)', borderTopColor:'var(--terracotta)', borderRadius:'50%', animation:'spin 0.8s linear infinite' }} />
    </div>
  );

  if (setupRequired) return <SetupPage />;
  if (!user) return <LoginPage />;

  if (showSettings) return (
    <div className="app">
      <AppShell
        activeView="settings"
        onNavigate={navigateApp}
        onAddRecipe={handleImportRecipe}
        onImportFolder={handleImportFolder}
        onImportRecipe={handleImportRecipe}
        onAddYarn={handleAddYarn}
        onAddTool={handleAddTool}
        queue={workQueue}
        onOpenImport={() => setImportOpen(true)}
        onOpenRecipe={(id, initialView = 'text') => openRecipe(id, initialView)}
        onCancelAI={async (id) => { await cancelAIJob(id).catch(() => {}); refreshWorkQueue(); }}
        onDismissAI={async (id) => { await dismissAIJob(id).catch(() => {}); refreshWorkQueue(); }}
      >
        <SettingsPage onBack={() => setShowSettings(false)} />
      </AppShell>
      {pendingAnnouncements.length > 0 && (
        <AnnouncementModal
          announcements={pendingAnnouncements}
          onDismiss={handleDismissAnnouncements}
        />
      )}
    </div>
  );

  if (showStats) return (
    <div className="app">
      <AppShell
        activeView="stats"
        onNavigate={navigateApp}
        onAddRecipe={handleImportRecipe}
        onImportFolder={handleImportFolder}
        onImportRecipe={handleImportRecipe}
        onAddYarn={handleAddYarn}
        onAddTool={handleAddTool}
        queue={workQueue}
        onOpenImport={() => setImportOpen(true)}
        onOpenRecipe={(id, initialView = 'text') => openRecipe(id, initialView)}
        onCancelAI={async (id) => { await cancelAIJob(id).catch(() => {}); refreshWorkQueue(); }}
        onDismissAI={async (id) => { await dismissAIJob(id).catch(() => {}); refreshWorkQueue(); }}
      >
        <StatisticsPage />
      </AppShell>
    </div>
  );

  if (showHelp) return (
    <div className="app">
      <AppShell
        activeView="help"
        onNavigate={navigateApp}
        onAddRecipe={handleImportRecipe}
        onImportFolder={handleImportFolder}
        onImportRecipe={handleImportRecipe}
        onAddYarn={handleAddYarn}
        onAddTool={handleAddTool}
        queue={workQueue}
        onOpenImport={() => setImportOpen(true)}
        onOpenRecipe={(id, initialView = 'text') => openRecipe(id, initialView)}
        onCancelAI={async (id) => { await cancelAIJob(id).catch(() => {}); refreshWorkQueue(); }}
        onDismissAI={async (id) => { await dismissAIJob(id).catch(() => {}); refreshWorkQueue(); }}
      >
        <HelpPage onBack={() => setShowHelp(false)} />
      </AppShell>
    </div>
  );

  return (
    <div className="app">
      <AppShell
        activeView={activeView}
        recipeMode={activeView === 'recipes' && Boolean(viewingRecipeId)}
        onNavigate={navigateApp}
        onAddRecipe={handleImportRecipe}
        onImportFolder={handleImportFolder}
        onImportRecipe={handleImportRecipe}
        onAddYarn={handleAddYarn}
        onAddTool={handleAddTool}
        onRecipeBack={() => { setViewingRecipeId(null); persistAppLocation({ activeView: 'recipes' }); }}
        queue={workQueue}
        onOpenImport={() => setImportOpen(true)}
        onOpenRecipe={(id, initialView = 'text') => openRecipe(id, initialView)}
        onCancelAI={async (id) => { await cancelAIJob(id).catch(() => {}); refreshWorkQueue(); }}
        onDismissAI={async (id) => { await dismissAIJob(id).catch(() => {}); refreshWorkQueue(); }}
      >

        {activeView === 'home' && (
          <HomePage
            onOpenRecipe={openRecipe}
            onNavigate={navigateApp}
            onAddRecipe={handleImportRecipe}
            workQueueDock={(
              <WorkQueueDock
                queue={workQueue}
                variant="mobile"
                onOpenImport={() => setImportOpen(true)}
                onOpenRecipe={(id, initialView = 'text') => openRecipe(id, initialView)}
                onCancelAI={async (id) => { await cancelAIJob(id).catch(() => {}); refreshWorkQueue(); }}
                onDismissAI={async (id) => { await dismissAIJob(id).catch(() => {}); refreshWorkQueue(); }}
              />
            )}
          />
        )}

        {/* ── Recipes ── */}
        {activeView === 'recipes' && (
          viewingRecipeId ? (
            <RecipeViewer
              recipeId={viewingRecipeId}
              initialViewMode={recipeInitialView}
              onBack={() => { setViewingRecipeId(null); persistAppLocation({ activeView: 'recipes' }); }}
              onDeleted={() => { setViewingRecipeId(null); setRefreshKey(k => k + 1); persistAppLocation({ activeView: 'recipes' }); }}
              onTextJobQueued={refreshWorkQueue}
            />
          ) : (
            <Library
              refreshKey={refreshKey}
              onRecipeClick={(id) => openRecipe(id, 'original')}
              onUploadClick={handleImportRecipe}
            />
          )
        )}

        {/* ── Inventory ── */}
        {activeView === 'inventory' && (
          <InventoryPage
            onRequestAddYarn={handleAddYarn}
            addRequest={inventoryAddRequest}
            refreshKey={inventoryRefreshKey}
            onYarnClick={openYarn}
          />
        )}

        {/* ── Yarn/thread detail, opened from the merged Inventory ── */}
        {activeView === 'yarnDatabase' && (
          viewingYarnId ? (
            <YarnViewer
              yarnId={viewingYarnId}
              onBack={() => { setActiveView('inventory'); setViewingYarnId(null); persistAppLocation({ activeView: 'inventory' }); }}
              onDeleted={() => {
                setActiveView('inventory');
                setViewingYarnId(null);
                setYarnRefreshKey(k => k + 1);
                setInventoryRefreshKey(k => k + 1);
                persistAppLocation({ activeView: 'inventory' });
              }}
            />
          ) : (
            <YarnLibrary
              key={yarnRefreshKey}
              onYarnClick={openYarn}
            />
          )
        )}

      </AppShell>

      {yarnUploadOpen && (
        <YarnUploadModal
          allowStockQuantity
          onClose={() => setYarnUploadOpen(false)}
          onSuccess={() => {
            setYarnUploadOpen(false);
            setYarnRefreshKey(k => k + 1);
            setInventoryRefreshKey(k => k + 1);
            setActiveView('inventory');
          }}
        />
      )}
      {importOpen && (
        <ImportWizard
          onClose={() => { setImportOpen(false); checkImport(); refreshWorkQueue(); }}
          onRecipeAdded={() => { setRefreshKey(k => k + 1); checkImport(); refreshWorkQueue(); }}
        />
      )}

      {/* Announcement popup — shown once per push to all users */}
      {pendingAnnouncements.length > 0 && (
        <AnnouncementModal
          announcements={pendingAnnouncements}
          onDismiss={handleDismissAnnouncements}
        />
      )}
    </div>
  );
}

export default function App() {
  return <AppProvider><AppInner /></AppProvider>;
}
