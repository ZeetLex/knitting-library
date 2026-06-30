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
import { getImportQueue, fetchPendingAnnouncements, dismissAnnouncement, fetchWorkQueue, cancelAIJob, dismissAIJob } from './utils/api';
import './App.css';

const APP_RESUME_PREFIX = 'knitting_app_resume_v1';

function appResumeKey(user) {
  return `${APP_RESUME_PREFIX}_${user?.id || user?.username || 'guest'}`;
}

function saveAppResume(user, data) {
  if (!user || !data?.recipeId) return;
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

function clearAppResume(user) {
  if (!user) return;
  try { localStorage.removeItem(appResumeKey(user)); } catch (_) {}
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
    clearAppResume(user);
    setActiveView(view);
    setViewingRecipeId(null);
    setViewingYarnId(null);
    setRecipeInitialView('original');
    setShowStats(false);
    setShowSettings(false);
    setShowHelp(false);
  };

  const navigateApp = (view) => {
    if (view === 'settings') {
      clearAppResume(user);
      setShowSettings(true);
      setShowStats(false);
      setShowHelp(false);
      setViewingRecipeId(null);
      setViewingYarnId(null);
      return;
    }
    if (view === 'stats') {
      clearAppResume(user);
      setShowStats(true);
      setShowSettings(false);
      setShowHelp(false);
      setViewingRecipeId(null);
      setViewingYarnId(null);
      return;
    }
    if (view === 'help') {
      clearAppResume(user);
      setShowHelp(true);
      setShowSettings(false);
      setShowStats(false);
      setViewingRecipeId(null);
      setViewingYarnId(null);
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
    saveAppResume(user, { activeView: 'recipes', recipeId: id, initialViewMode: initialView });
  };

  const openYarn = (id) => {
    setActiveView('yarnDatabase');
    setViewingYarnId(id);
  };

  const handleImportRecipe = () => {
    clearAppResume(user);
    setActiveView('recipes');
    setViewingRecipeId(null);
    setRecipeInitialView('original');
    setImportOpen(true);
  };

  const handleImportFolder = () => {
    handleImportRecipe();
  };

  const handleAddYarn = () => {
    clearAppResume(user);
    setActiveView('inventory');
    setViewingYarnId(null);
    setYarnUploadOpen(true);
  };

  const handleAddTool = () => {
    clearAppResume(user);
    setActiveView('inventory');
    setViewingRecipeId(null);
    setViewingYarnId(null);
    setShowSettings(false);
    setShowStats(false);
    setShowHelp(false);
    setInventoryAddRequest({ type: 'tool', nonce: Date.now() });
  };

  useEffect(() => {
    if (!user) {
      resumeCheckedRef.current = false;
      return;
    }
    if (resumeCheckedRef.current) return;
    resumeCheckedRef.current = true;
    const saved = readAppResume(user);
    if (saved?.activeView === 'recipes' && saved.recipeId) {
      setActiveView('recipes');
      setShowSettings(false);
      setShowStats(false);
      setShowHelp(false);
      setRecipeInitialView(saved.initialViewMode || 'original');
      setViewingRecipeId(saved.recipeId);
    }
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
        onRecipeBack={() => { clearAppResume(user); setViewingRecipeId(null); }}
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
              onBack={() => { clearAppResume(user); setViewingRecipeId(null); }}
              onDeleted={() => { clearAppResume(user); setViewingRecipeId(null); setRefreshKey(k => k + 1); }}
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
              onBack={() => { setActiveView('inventory'); setViewingYarnId(null); }}
              onDeleted={() => {
                setActiveView('inventory');
                setViewingYarnId(null);
                setYarnRefreshKey(k => k + 1);
                setInventoryRefreshKey(k => k + 1);
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
