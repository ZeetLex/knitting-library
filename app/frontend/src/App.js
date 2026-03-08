import React, { useState, useCallback } from 'react';
import { AppProvider, useApp } from './utils/AppContext';
import LoginPage from './pages/LoginPage';
import Library from './pages/Library';
import RecipeViewer from './pages/RecipeViewer';
import SettingsPage from './pages/SettingsPage';
import UploadModal from './components/UploadModal';
import Header from './components/Header';
import './App.css';

function AppInner() {
  const { user, loading } = useApp();
  const [viewingRecipeId, setViewingRecipeId] = useState(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleUploadSuccess = useCallback(() => {
    setUploadOpen(false);
    setRefreshKey(k => k + 1);
  }, []);

  if (loading) return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100vh', background:'var(--bg-primary)' }}>
      <div style={{ width:36, height:36, border:'3px solid var(--border)', borderTopColor:'var(--terracotta)', borderRadius:'50%', animation:'spin 0.8s linear infinite' }} />
    </div>
  );

  if (!user) return <LoginPage />;

  if (showSettings) return (
    <div className="app">
      <Header
        onUploadClick={() => setUploadOpen(true)}
        onLogoClick={() => { setShowSettings(false); setViewingRecipeId(null); }}
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
        onUploadClick={() => setUploadOpen(true)}
        onLogoClick={() => setViewingRecipeId(null)}
        onSettingsClick={() => setShowSettings(true)}
      />
      <main className="app-main">
        {viewingRecipeId ? (
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
        )}
      </main>
      {uploadOpen && (
        <UploadModal onClose={() => setUploadOpen(false)} onSuccess={handleUploadSuccess} />
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
