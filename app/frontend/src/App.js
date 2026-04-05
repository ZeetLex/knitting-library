import React, { useState, useCallback, useEffect } from 'react';
import { AppProvider, useApp } from './utils/AppContext';
import LoginPage from './pages/LoginPage';
import Library from './pages/Library';
import RecipeViewer from './pages/RecipeViewer';
import YarnLibrary from './pages/YarnLibrary';
import YarnViewer from './pages/YarnViewer';
import InventoryPage from './pages/InventoryPage';
import SettingsPage from './pages/SettingsPage';
import StatisticsPage from './pages/StatisticsPage';
import UploadModal from './components/UploadModal';
import YarnUploadModal from './components/YarnUploadModal';
import ImportWizard from './components/ImportWizard';
import Header from './components/Header';
import AnnouncementModal from './components/AnnouncementModal';
import { getImportQueue, fetchPendingAnnouncements, dismissAnnouncement } from './utils/api';
import './App.css';

function AppInner() {
  const { user, loading, t } = useApp();
  const [activeTab, setActiveTab]             = useState('recipes');
  const [yarnSubTab, setYarnSubTab]           = useState('inventory');
  const [viewingRecipeId, setViewingRecipeId] = useState(null);
  const [viewingYarnId, setViewingYarnId]     = useState(null);
  const [uploadOpen, setUploadOpen]           = useState(false);
  const [yarnUploadOpen, setYarnUploadOpen]   = useState(false);
  const [importOpen, setImportOpen]           = useState(false);
  const [importCount, setImportCount]         = useState(0);
  const [showSettings, setShowSettings]       = useState(false);
  const [showStats, setShowStats]             = useState(false);
  const [refreshKey, setRefreshKey]           = useState(0);
  const [yarnRefreshKey, setYarnRefreshKey]   = useState(0);

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

  const handleAddClick = () => {
    if (activeTab === 'yarns' && yarnSubTab === 'yarndatabase') setYarnUploadOpen(true);
    else if (activeTab === 'recipes') setUploadOpen(true);
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setViewingRecipeId(null);
    setViewingYarnId(null);
    setShowStats(false);
    setShowSettings(false);
  };

  const handleYarnSubTabChange = (sub) => {
    setYarnSubTab(sub);
    setViewingYarnId(null);
  };

  // Header button label
  const addLabel = activeTab === 'yarns' && yarnSubTab === 'yarndatabase'
    ? t('addYarn')
    : activeTab === 'recipes' ? t('addRecipe')
    : null; // inventory manages its own add buttons

  const sharedHeaderProps = {
    activeTab,
    onTabChange: handleTabChange,
    onUploadClick: handleAddClick,
    onBulkImportClick: () => setImportOpen(true),
    onSettingsClick: () => setShowSettings(true),
    addLabel,
    importCount,
    yarnSubTab,
    onYarnSubTabChange: handleYarnSubTabChange,
    onStatsClick: () => { setShowSettings(false); setShowStats(true); },
  };

  if (loading) return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100vh', background:'var(--bg-primary)' }}>
      <div style={{ width:36, height:36, border:'3px solid var(--border)', borderTopColor:'var(--terracotta)', borderRadius:'50%', animation:'spin 0.8s linear infinite' }} />
    </div>
  );

  if (!user) return <LoginPage />;

  if (showSettings) return (
    <div className="app">
      <Header {...sharedHeaderProps} onLogoClick={() => { setShowSettings(false); setViewingRecipeId(null); setViewingYarnId(null); }} />
      <main className={`app-main${activeTab === 'yarns' ? ' app-main--with-subtabs' : ''}`}>
        <SettingsPage onBack={() => setShowSettings(false)} />
      </main>
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
      <Header {...sharedHeaderProps} onLogoClick={() => { setShowStats(false); setViewingRecipeId(null); setViewingYarnId(null); }} />
      <main className="app-main">
        <StatisticsPage />
      </main>
    </div>
  );

  return (
    <div className="app">
      <Header {...sharedHeaderProps} onLogoClick={() => { setViewingRecipeId(null); setViewingYarnId(null); }} />
      <main className={`app-main${activeTab === 'yarns' ? ' app-main--with-subtabs' : ''}`}>

        {/* ── Recipes tab ── */}
        {activeTab === 'recipes' && (
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

        {/* ── Inventory / Yarn Database tab ── */}
        {activeTab === 'yarns' && (
          <>
            {yarnSubTab === 'inventory' && (
              <InventoryPage
                onRequestAddYarn={() => { setYarnSubTab('yarndatabase'); setYarnUploadOpen(true); }}
              />
            )}
            {yarnSubTab === 'yarndatabase' && (
              viewingYarnId ? (
                <YarnViewer
                  yarnId={viewingYarnId}
                  onBack={() => setViewingYarnId(null)}
                  onDeleted={() => { setViewingYarnId(null); setYarnRefreshKey(k => k + 1); }}
                />
              ) : (
                <YarnLibrary
                  key={yarnRefreshKey}
                  onYarnClick={setViewingYarnId}
                />
              )
            )}
          </>
        )}

      </main>

      {uploadOpen && (
        <UploadModal onClose={() => setUploadOpen(false)} onSuccess={handleUploadSuccess} />
      )}
      {yarnUploadOpen && (
        <YarnUploadModal
          onClose={() => setYarnUploadOpen(false)}
          onSuccess={() => { setYarnUploadOpen(false); setYarnRefreshKey(k => k + 1); }}
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
