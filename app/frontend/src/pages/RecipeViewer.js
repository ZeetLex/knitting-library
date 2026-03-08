/**
 * RecipeViewer.js
 * Shows a single recipe in detail.
 * - If the recipe is a PDF: shows an embedded PDF viewer
 * - If the recipe is images: shows a swipeable image gallery
 * Also shows the recipe's metadata (title, tags, etc.)
 * and has an Edit and Delete button.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  ArrowLeft, ChevronLeft, ChevronRight, ZoomIn, ZoomOut,
  Maximize2, Pencil, Trash2, Tag, FolderOpen, X
} from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchRecipe, deleteRecipe, updateRecipe, fetchCategories, pdfUrl, imageUrl } from '../utils/api';
import './RecipeViewer.css';

export default function RecipeViewer({ recipeId, onBack, onDeleted }) {
  const [recipe, setRecipe]       = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [imageIndex, setImageIndex] = useState(0);
  const [zoom, setZoom]           = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const [editing, setEditing]     = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const touchStartX = useRef(null);

  // Load the recipe data
  useEffect(() => {
    setLoading(true);
    fetchRecipe(recipeId)
      .then(setRecipe)
      .catch(() => setError('Could not load this recipe.'))
      .finally(() => setLoading(false));
  }, [recipeId]);

  // Keyboard navigation for image recipes
  const handleKey = useCallback((e) => {
    if (!recipe || recipe.file_type !== 'images') return;
    if (e.key === 'ArrowLeft')  setImageIndex(i => Math.max(0, i - 1));
    if (e.key === 'ArrowRight') setImageIndex(i => Math.min(recipe.images.length - 1, i + 1));
    if (e.key === 'Escape') setFullscreen(false);
  }, [recipe]);

  useEffect(() => {
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  // Touch/swipe support for image recipes
  const handleTouchStart = (e) => {
    touchStartX.current = e.touches[0].clientX;
  };

  const handleTouchEnd = (e) => {
    if (touchStartX.current === null || !recipe) return;
    const delta = touchStartX.current - e.changedTouches[0].clientX;
    if (Math.abs(delta) > 50) {
      if (delta > 0) setImageIndex(i => Math.min(recipe.images.length - 1, i + 1));
      else           setImageIndex(i => Math.max(0, i - 1));
    }
    touchStartX.current = null;
  };

  const handleDelete = async () => {
    try {
      await deleteRecipe(recipeId);
      onDeleted();
    } catch (e) {
      alert('Failed to delete recipe. Please try again.');
    }
  };

  if (loading) return (
    <div className="viewer-loading">
      <div className="spinner" />
      <p>Loading recipe…</p>
    </div>
  );

  if (error || !recipe) return (
    <div className="viewer-error">
      <p>{error || 'Recipe not found'}</p>
      <button className="btn-back" onClick={onBack}>← Back to Library</button>
    </div>
  );

  return (
    <div className="viewer">
      {/* ─── Top Bar ───────────────────────────────────────────────────────── */}
      <div className="viewer-topbar">
        <button className="viewer-back" onClick={onBack} aria-label="Back">
          <ArrowLeft size={20} />
          <span>Library</span>
        </button>

        <div className="viewer-actions">
          <button className="viewer-action-btn" onClick={() => setEditing(true)} title="Edit metadata">
            <Pencil size={18} />
          </button>
          <button className="viewer-action-btn danger" onClick={() => setDeleteConfirm(true)} title="Delete recipe">
            <Trash2 size={18} />
          </button>
        </div>
      </div>

      <div className="viewer-body">
        {/* ─── Recipe Content ─────────────────────────────────────────────── */}
        <div className="viewer-content">
          {recipe.file_type === 'pdf' ? (
            /* PDF Viewer */
            <div className="pdf-container">
              <div className="pdf-controls">
                <button onClick={() => setZoom(z => Math.max(0.5, z - 0.25))} title="Zoom out">
                  <ZoomOut size={18} />
                </button>
                <span>{Math.round(zoom * 100)}%</span>
                <button onClick={() => setZoom(z => Math.min(3, z + 0.25))} title="Zoom in">
                  <ZoomIn size={18} />
                </button>
                <button onClick={() => setZoom(1)} title="Reset zoom">Reset</button>
                <a
                  href={pdfUrl(recipeId)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="pdf-open-btn"
                  title="Open PDF in new tab"
                >
                  <Maximize2 size={18} />
                  <span>Open Full</span>
                </a>
              </div>
              <div className="pdf-frame-wrap" style={{ transform: `scale(${zoom})`, transformOrigin: 'top center' }}>
                <iframe
                  src={`${pdfUrl(recipeId)}#toolbar=1&navpanes=1`}
                  title={recipe.title}
                  className="pdf-frame"
                />
              </div>
            </div>
          ) : (
            /* Image Viewer */
            <div
              className={`image-viewer ${fullscreen ? 'fullscreen' : ''}`}
              onTouchStart={handleTouchStart}
              onTouchEnd={handleTouchEnd}
            >
              {/* Main image */}
              <div className="image-viewer-main">
                {recipe.images.length > 0 ? (
                  <img
                    key={imageIndex}
                    src={imageUrl(recipeId, recipe.images[imageIndex])}
                    alt={`${recipe.title} - page ${imageIndex + 1}`}
                    className="recipe-image fade-in"
                    style={{ transform: `scale(${zoom})` }}
                  />
                ) : (
                  <div className="image-placeholder">No images found</div>
                )}
              </div>

              {/* Navigation arrows */}
              {recipe.images.length > 1 && (
                <>
                  <button
                    className="image-nav prev"
                    onClick={() => setImageIndex(i => Math.max(0, i - 1))}
                    disabled={imageIndex === 0}
                    aria-label="Previous image"
                  >
                    <ChevronLeft size={28} />
                  </button>
                  <button
                    className="image-nav next"
                    onClick={() => setImageIndex(i => Math.min(recipe.images.length - 1, i + 1))}
                    disabled={imageIndex === recipe.images.length - 1}
                    aria-label="Next image"
                  >
                    <ChevronRight size={28} />
                  </button>
                </>
              )}

              {/* Image controls */}
              <div className="image-controls">
                <button onClick={() => setZoom(z => Math.max(0.5, z - 0.25))}><ZoomOut size={16} /></button>
                <button onClick={() => setZoom(1)}>Reset</button>
                <button onClick={() => setZoom(z => Math.min(4, z + 0.25))}><ZoomIn size={16} /></button>
                <button onClick={() => { setFullscreen(f => !f); setZoom(1); }}>
                  <Maximize2 size={16} />
                </button>
                {fullscreen && (
                  <button onClick={() => setFullscreen(false)}><X size={16} /></button>
                )}
              </div>

              {/* Page indicator */}
              {recipe.images.length > 1 && (
                <div className="image-indicator">
                  <span>{imageIndex + 1} / {recipe.images.length}</span>
                </div>
              )}

              {/* Thumbnail strip for multi-image recipes */}
              {recipe.images.length > 1 && (
                <div className="image-strip">
                  {recipe.images.map((img, i) => (
                    <button
                      key={img}
                      className={`strip-thumb ${i === imageIndex ? 'active' : ''}`}
                      onClick={() => setImageIndex(i)}
                      aria-label={`Go to page ${i + 1}`}
                    >
                      <img
                        src={imageUrl(recipeId, img)}
                        alt={`Page ${i + 1}`}
                        loading="lazy"
                      />
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ─── Sidebar (metadata) ─────────────────────────────────────────── */}
        <aside className="viewer-sidebar">
          <h1 className="viewer-title">{recipe.title}</h1>

          {recipe.description && (
            <p className="viewer-description">{recipe.description}</p>
          )}

          {recipe.categories.length > 0 && (
            <div className="viewer-meta-group">
              <div className="viewer-meta-label">
                <FolderOpen size={14} />
                <span>Categories</span>
              </div>
              <div className="viewer-meta-pills">
                {recipe.categories.map(cat => (
                  <span key={cat} className="meta-pill category-pill">{cat}</span>
                ))}
              </div>
            </div>
          )}

          {recipe.tags.length > 0 && (
            <div className="viewer-meta-group">
              <div className="viewer-meta-label">
                <Tag size={14} />
                <span>Tags</span>
              </div>
              <div className="viewer-meta-pills">
                {recipe.tags.map(tag => (
                  <span key={tag} className="meta-pill">{tag}</span>
                ))}
              </div>
            </div>
          )}

          <p className="viewer-date">
            Added {new Date(recipe.created_date).toLocaleDateString('en-US', {
              year: 'numeric', month: 'long', day: 'numeric'
            })}
          </p>
        </aside>
      </div>

      {/* ─── Edit Modal ──────────────────────────────────────────────────────── */}
      {editing && (
        <EditModal
          recipe={recipe}
          onClose={() => setEditing(false)}
          onSaved={(updated) => {
            setRecipe(updated);
            setEditing(false);
          }}
        />
      )}

      {/* ─── Delete Confirmation ─────────────────────────────────────────────── */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(false)}>
          <div className="confirm-modal" onClick={e => e.stopPropagation()}>
            <h3>Delete Recipe?</h3>
            <p>This will permanently delete <strong>{recipe.title}</strong> and all its files. This cannot be undone.</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteConfirm(false)}>Cancel</button>
              <button className="btn-danger" onClick={handleDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Edit Modal ──────────────────────────────────────────────────────────────── */
function EditModal({ recipe, onClose, onSaved }) {
  const [title, setTitle]         = useState(recipe.title);
  const [description, setDesc]    = useState(recipe.description || '');
  const [categories, setCategories] = useState([]);
  const [selCats, setSelCats]     = useState(recipe.categories);
  const [tagInput, setTagInput]   = useState(recipe.tags.join(', '));
  const [saving, setSaving]       = useState(false);

  useEffect(() => {
    fetchCategories().then(setCategories).catch(console.error);
  }, []);

  const toggleCat = (cat) => {
    setSelCats(prev => prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]);
  };

  const handleSave = async () => {
    if (!title.trim()) return alert('Please enter a recipe name.');
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('title', title.trim());
      fd.append('description', description.trim());
      fd.append('categories', selCats.join(','));
      fd.append('tags', tagInput);
      const updated = await updateRecipe(recipe.id, fd);
      onSaved(updated);
    } catch (e) {
      alert('Failed to save. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="edit-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Edit Recipe</h3>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>

        <div className="modal-body">
          <label className="form-label">Recipe Name *</label>
          <input
            className="form-input"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="e.g. Cozy Cable Socks"
          />

          <label className="form-label">Notes / Description</label>
          <textarea
            className="form-input form-textarea"
            value={description}
            onChange={e => setDesc(e.target.value)}
            placeholder="Optional notes about this pattern…"
            rows={3}
          />

          <label className="form-label">Categories</label>
          <div className="form-pills">
            {categories.map(cat => (
              <button
                key={cat}
                type="button"
                className={`pill ${selCats.includes(cat) ? 'pill-active' : ''}`}
                onClick={() => toggleCat(cat)}
              >
                {cat}
              </button>
            ))}
          </div>

          <label className="form-label">
            Tags
            <span className="form-hint"> — separate with commas</span>
          </label>
          <input
            className="form-input"
            value={tagInput}
            onChange={e => setTagInput(e.target.value)}
            placeholder="e.g. wool, fingering weight, easy"
          />
        </div>

        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
