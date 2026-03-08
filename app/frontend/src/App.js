/**
 * App.js
 * The root of the application. Manages which "page" is shown:
 *   - Library (the recipe grid)
 *   - Recipe viewer (single recipe)
 *   - Upload form
 */

import React, { useState, useCallback } from 'react';
import Library from './pages/Library';
import RecipeViewer from './pages/RecipeViewer';
import UploadModal from './components/UploadModal';
import Header from './components/Header';
import './App.css';

export default function App() {
  // Which recipe is currently being viewed (null = show grid)
  const [viewingRecipeId, setViewingRecipeId] = useState(null);
  // Whether the upload modal is open
  const [uploadOpen, setUploadOpen] = useState(false);
  // A counter used to trigger re-fetching the recipe list after uploads
  const [refreshKey, setRefreshKey] = useState(0);

  const handleUploadSuccess = useCallback(() => {
    setUploadOpen(false);
    setRefreshKey(k => k + 1); // This causes the Library to re-fetch recipes
  }, []);

  return (
    <div className="app">
      <Header
        onUploadClick={() => setUploadOpen(true)}
        onLogoClick={() => setViewingRecipeId(null)}
      />

      <main className="app-main">
        {viewingRecipeId ? (
          <RecipeViewer
            recipeId={viewingRecipeId}
            onBack={() => setViewingRecipeId(null)}
            onDeleted={() => {
              setViewingRecipeId(null);
              setRefreshKey(k => k + 1);
            }}
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
        <UploadModal
          onClose={() => setUploadOpen(false)}
          onSuccess={handleUploadSuccess}
        />
      )}
    </div>
  );
}
