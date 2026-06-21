import React, { useState, useCallback, useEffect } from 'react';
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
import UploadModal from './components/UploadModal';
import YarnUploadModal from './components/YarnUploadModal';
import ImportWizard from './components/ImportWizard';
import AppShell from './components/AppShell';
import AnnouncementModal from './components/AnnouncementModal';
import { getImportQueue, fetchPendingAnnouncements, dismissAnnouncement } from './utils/api';
import './App.css';

function AppInner() {
  const { user, loading, setupRequired, t } = useApp();
  const [activeView, setActiveView]           = useState('home');
  const [viewingRecipeId, setViewingRecipeId] = useState(null);
  const [viewingYarnId, setViewingYarnId]     = useState(null);
  const [uploadOpen, setUploadOpen]           = useState(false);
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

  const checkImport = useCallback(() => {
    getImportQueue().then(r => setImportCount(r.count || 0)).catch(() => {});
  }, []);

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
  useEffect(() => { if (user) checkImport(); }, [user, checkImport]);

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

  const handleUploadSuccess = useCallback(() => {
    setUploadOpen(false);
    setRefreshKey(k => k + 1);
  }, []);

  const handleNavigate = (view) => {
    setActiveView(view);
    setViewingRecipeId(null);
    setViewingYarnId(null);
    setShowStats(false);
    setShowSettings(false);
    setShowHelp(false);
  };

  const navigateApp = (view) => {
    if (view === 'settings') {
      setShowSettings(true);
      setShowStats(false);
      setShowHelp(false);
      setViewingRecipeId(null);
      setViewingYarnId(null);
      return;
    }
    if (view === 'stats') {
      setShowStats(true);
      setShowSettings(false);
      setShowHelp(false);
      setViewingRecipeId(null);
      setViewingYarnId(null);
      return;
    }
    if (view === 'help') {
      setShowHelp(true);
      setShowSettings(false);
      setShowStats(false);
      setViewingRecipeId(null);
      setViewingYarnId(null);
      return;
    }
    handleNavigate(view);
  };

  const openRecipe = (id) => {
    setActiveView('recipes');
    setViewingRecipeId(id);
  };

  const openYarn = (id) => {
    setActiveView('yarnDatabase');
    setViewingYarnId(id);
  };

  const handleAddRecipe = () => {
    setActiveView('recipes');
    setViewingRecipeId(null);
    setUploadOpen(true);
  };

  const handleImportFolder = () => {
    setActiveView('recipes');
    setViewingRecipeId(null);
    setImportOpen(true);
  };

  const handleAddYarn = () => {
    setActiveView('inventory');
    setViewingYarnId(null);
    setYarnUploadOpen(true);
  };

  const handleAddTool = () => {
    setActiveView('inventory');
    setViewingRecipeId(null);
    setViewingYarnId(null);
    setShowSettings(false);
    setShowStats(false);
    setShowHelp(false);
    setInventoryAddRequest({ type: 'tool', nonce: Date.now() });
  };

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
        onAddRecipe={handleAddRecipe}
        onImportFolder={handleImportFolder}
        onAddYarn={handleAddYarn}
        onAddTool={handleAddTool}
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
        onAddRecipe={handleAddRecipe}
        onImportFolder={handleImportFolder}
        onAddYarn={handleAddYarn}
        onAddTool={handleAddTool}
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
        onAddRecipe={handleAddRecipe}
        onImportFolder={handleImportFolder}
        onAddYarn={handleAddYarn}
        onAddTool={handleAddTool}
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
        onAddRecipe={handleAddRecipe}
        onImportFolder={handleImportFolder}
        onAddYarn={handleAddYarn}
        onAddTool={handleAddTool}
        onRecipeBack={() => setViewingRecipeId(null)}
      >

        {activeView === 'home' && (
          <HomePage
            onOpenRecipe={openRecipe}
            onNavigate={navigateApp}
            onAddRecipe={handleAddRecipe}
          />
        )}

        {/* ── Recipes ── */}
        {activeView === 'recipes' && (
          viewingRecipeId ? (
            <RecipeViewer
              recipeId={viewingRecipeId}
              onBack={() => setViewingRecipeId(null)}
              onDeleted={() => { setViewingRecipeId(null); setRefreshKey(k => k + 1); }}
            />
          ) : (
            <Library
              refreshKey={refreshKey}
              onRecipeClick={setViewingRecipeId}
              onUploadClick={() => setUploadOpen(true)}
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

      {uploadOpen && (
        <UploadModal onClose={() => setUploadOpen(false)} onSuccess={handleUploadSuccess} />
      )}
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
          onClose={() => { setImportOpen(false); checkImport(); }}
          onRecipeAdded={() => { setRefreshKey(k => k + 1); checkImport(); }}
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
