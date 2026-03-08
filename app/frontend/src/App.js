import React, { useState, useCallback } from 'react';
import { AppProvider, useApp } from './utils/AppContext';
import LoginPage from './pages/LoginPage';
import Library from './pages/Library';
import RecipeViewer from './pages/RecipeViewer';
import YarnLibrary from './pages/YarnLibrary';
import YarnViewer from './pages/YarnViewer';
import SettingsPage from './pages/SettingsPage';
import UploadModal from './components/UploadModal';
import YarnUploadModal from './components/YarnUploadModal';
import Header from './components/Header';
import './App.css';

function AppInner() {
  const { user, loading } = useApp();
  const [activeTab, setActiveTab]           = useState('recipes');
  const [viewingRecipeId, setViewingRecipeId] = useState(null);
  const [viewingYarnId, setViewingYarnId]   = useState(null);
  const [uploadOpen, setUploadOpen]         = useState(false);
  const [yarnUploadOpen, setYarnUploadOpen] = useState(false);
  const [showSettings, setShowSettings]     = useState(false);
  const [refreshKey, setRefreshKey]         = useState(0);
  const [yarnRefreshKey, setYarnRefreshKey] = useState(0);

  const handleUploadSuccess = useCallback(() => {
    setUploadOpen(false);
    setRefreshKey(k => k + 1);
  }, []);

  const handleAddClick = () => {
    if (activeTab === 'yarns') setYarnUploadOpen(true);
    else setUploadOpen(true);
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setViewingRecipeId(null);
    setViewingYarnId(null);
  };

  if (loading) return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100vh', background:'var(--bg-primary)' }}>
      <div style={{ width:36, height:36, border:'3px solid var(--border)', borderTopColor:'var(--terracotta)', borderRadius:'50%', animation:'spin 0.8s linear infinite' }} />
    </div>
  );

  if (!user) return <LoginPage />;

  if (showSettings) return (
    <div className="app">
      <Header
        activeTab={activeTab}
        onTabChange={handleTabChange}
        onUploadClick={handleAddClick}
        onLogoClick={() => { setShowSettings(false); setViewingRecipeId(null); setViewingYarnId(null); }}
        onSettingsClick={() => setShowSettings(true)}
      />
      <main className="app-main">
        <SettingsPage onBack={() => setShowSettings(false)} />
      </main>
    </div>
  );

  return (
    <div className="app">
      <Header
        activeTab={activeTab}
        onTabChange={handleTabChange}
        onUploadClick={handleAddClick}
        onLogoClick={() => { setViewingRecipeId(null); setViewingYarnId(null); }}
        onSettingsClick={() => setShowSettings(true)}
      />
      <main className="app-main">
        {/* ── Recipes tab ─────────────────────────────────────────── */}
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

        {/* ── Yarns tab ────────────────────────────────────────────── */}
        {activeTab === 'yarns' && (
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
      </main>

      {/* Recipe upload modal */}
      {uploadOpen && (
        <UploadModal onClose={() => setUploadOpen(false)} onSuccess={handleUploadSuccess} />
      )}

      {/* Yarn upload modal (from header + button) */}
      {yarnUploadOpen && (
        <YarnUploadModal
          onClose={() => setYarnUploadOpen(false)}
          onSuccess={() => { setYarnUploadOpen(false); setYarnRefreshKey(k => k + 1); }}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppInner />
    </AppProvider>
  );
}
