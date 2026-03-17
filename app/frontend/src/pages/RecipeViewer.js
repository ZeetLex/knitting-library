import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, ZoomIn, ZoomOut, Maximize2, Pencil, Trash2, Tag, FolderOpen, X } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchRecipe, deleteRecipe, updateRecipe, fetchCategories, pdfUrl, imageUrl, fetchPdfPages, convertPdf, pdfPageUrl } from '../utils/api';
import { ImageAnnotationCanvas } from '../components/AnnotationCanvas';
import ProjectStatus from '../components/ProjectStatus';
import KnittingToolbar from '../components/KnittingToolbar';
import './RecipeViewer.css';

export default function RecipeViewer({ recipeId, onBack, onDeleted }) {
  const { t } = useApp();
  const [recipe, setRecipe]         = useState(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [imageIndex, setImageIndex] = useState(0);
  const [zoom, setZoom]             = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const [editing, setEditing]       = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [pdfPages, setPdfPages]     = useState([]);
  const [converting, setConverting] = useState(false);
  const touchStartX = useRef(null);

  useEffect(() => {
    setLoading(true);
    fetchRecipe(recipeId)
      .then(r => {
        setRecipe(r);
        if (r.file_type === 'pdf') {
          fetchPdfPages(recipeId).then(d => {
            const pages = d.pages || [];
            if (pages.length > 0) {
              setPdfPages(pages);
            } else {
              // Auto-convert on first view
              setConverting(true);
              convertPdf(recipeId)
                .then(d2 => setPdfPages(d2.pages || []))
                .catch(() => {})
                .finally(() => setConverting(false));
            }
          });
        }
      })
      .catch(() => setError('Could not load this recipe.'))
      .finally(() => setLoading(false));
  }, [recipeId]);

  const handleKey = useCallback((e) => {
    if (e.key === 'Escape') setFullscreen(false);
    if (!recipe || recipe.file_type !== 'images') return;
    if (e.key === 'ArrowLeft')  setImageIndex(i => Math.max(0, i - 1));
    if (e.key === 'ArrowRight') setImageIndex(i => Math.min(recipe.images.length - 1, i + 1));
  }, [recipe]);

  useEffect(() => {
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  const handleTouchStart = (e) => { touchStartX.current = e.touches[0].clientX; };
  const handleTouchEnd   = (e) => {
    if (touchStartX.current === null || !recipe) return;
    const delta = touchStartX.current - e.changedTouches[0].clientX;
    if (Math.abs(delta) > 50) {
      if (delta > 0) setImageIndex(i => Math.min(recipe.images.length - 1, i + 1));
      else           setImageIndex(i => Math.max(0, i - 1));
    }
    touchStartX.current = null;
  };

  const handleDelete = async () => {
    try { await deleteRecipe(recipeId); onDeleted(); }
    catch (e) { alert('Failed to delete recipe.'); }
  };

  if (loading) return (
    <div className="viewer-loading">
      <div className="spinner" /><p>Loading…</p>
    </div>
  );

  if (error || !recipe) return (
    <div className="viewer-error">
      <p>{error || 'Recipe not found'}</p>
      <button className="btn-back" onClick={onBack}>← {t('backToLibrary')}</button>
    </div>
  );

  return (
    <div className="viewer">
      <div className="viewer-topbar">
        <button className="viewer-back" onClick={onBack}>
          <ArrowLeft size={20} /><span>{t('backToLibrary')}</span>
        </button>
        <div className="viewer-actions">
          <button className="viewer-action-btn" onClick={() => setEditing(true)} title={t('editRecipe')}>
            <Pencil size={18} />
          </button>
          <button className="viewer-action-btn danger" onClick={() => setDeleteConfirm(true)} title={t('deleteRecipe')}>
            <Trash2 size={18} />
          </button>
        </div>
      </div>

      <div className="viewer-body">
        <div className="viewer-content">
          {recipe.file_type === 'pdf' ? (
            <div className={`pdf-container ${fullscreen ? 'pdf-fullscreen' : ''}`}>
              <div className="pdf-controls">
                <button className="pdf-open-btn" onClick={() => { setFullscreen(f => !f); }}>
                  <Maximize2 size={18} />
                  <span>{fullscreen ? t('exitFullscreen') : t('openFull')}</span>
                </button>
                {fullscreen && (
                  <button className="pdf-exit-btn" onClick={() => setFullscreen(false)}>
                    <X size={18} />
                  </button>
                )}
                {/* Download original PDF */}
                <a href={pdfUrl(recipeId)} download className="pdf-download-btn">
                  ↓ PDF
                </a>
              </div>

              <div className="pdf-pages-wrap">
                {pdfPages.length > 0 ? (
                  // Render each page as an annotatable image
                  pdfPages.map((page, i) => (
                    <div key={page} className="pdf-page-block">
                      <div className="pdf-page-number">{t('pdfPage')} {i + 1}</div>
                      <ImageAnnotationCanvas
                        recipeId={recipeId}
                        pageKey={page}
                        src={pdfPageUrl(recipeId, page)}
                      />
                    </div>
                  ))
                ) : (
                  // Pages not generated yet — show convert button or spinner
                  <div className="pdf-convert-prompt">
                    {converting ? (
                      <div className="pdf-converting">
                        <div className="spinner" />
                        <p>{t('convertingPdf')}</p>
                      </div>
                    ) : (
                      <>
                        <p>{t('pdfNotConverted')}</p>
                        <button className="btn-primary" onClick={async () => {
                          setConverting(true);
                          try {
                            const d = await convertPdf(recipeId);
                            setPdfPages(d.pages || []);
                          } catch(e) { alert('Conversion failed'); }
                          finally { setConverting(false); }
                        }}>
                          {t('convertPdfBtn')}
                        </button>
                        <p className="pdf-convert-note">{t('pdfConvertNote')}</p>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className={`image-viewer ${fullscreen ? 'fullscreen' : ''}`}
              onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
              <div className="image-viewer-main">
                {recipe.images.length > 0 ? (
                  <ImageAnnotationCanvas
                    recipeId={recipeId}
                    pageKey={recipe.images[imageIndex]}
                    src={imageUrl(recipeId, recipe.images[imageIndex])}
                    zoom={zoom}
                  />
                ) : (
                  <div className="image-placeholder">{t('noImages')}</div>
                )}
              </div>

              {recipe.images.length > 1 && (
                <>
                  <button className="image-nav prev" onClick={() => setImageIndex(i => Math.max(0, i-1))}
                    disabled={imageIndex === 0}><ChevronLeft size={28} /></button>
                  <button className="image-nav next" onClick={() => setImageIndex(i => Math.min(recipe.images.length-1, i+1))}
                    disabled={imageIndex === recipe.images.length-1}><ChevronRight size={28} /></button>
                </>
              )}

              <div className="image-controls">
                <button onClick={() => setZoom(z => Math.max(0.5, z-0.25))}><ZoomOut size={16} /></button>
                <button onClick={() => setZoom(1)}>{t('resetZoom')}</button>
                <button onClick={() => setZoom(z => Math.min(4, z+0.25))}><ZoomIn size={16} /></button>
                <button onClick={() => { setFullscreen(f => !f); setZoom(1); }}><Maximize2 size={16} /></button>
                {fullscreen && <button onClick={() => setFullscreen(false)}><X size={16} /></button>}
              </div>

              {recipe.images.length > 1 && (
                <div className="image-indicator">
                  <span>{imageIndex + 1} / {recipe.images.length}</span>
                </div>
              )}

              {recipe.images.length > 1 && (
                <div className="image-strip">
                  {recipe.images.map((img, i) => (
                    <button key={img} className={`strip-thumb ${i === imageIndex ? 'active' : ''}`}
                      onClick={() => setImageIndex(i)}>
                      <img src={imageUrl(recipeId, img)} alt={`${t('pdfPage')} ${i+1}`} loading="lazy" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <aside className={`viewer-sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
          {/* Mobile toggle handle */}
          <button
            className="sidebar-mobile-toggle"
            onClick={() => setSidebarOpen(o => !o)}
            aria-label="Toggle info panel"
          >
            <span className="sidebar-toggle-label">
              {sidebarOpen ? t('hideInfo') : t('showInfo')}
            </span>
            {sidebarOpen ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
          </button>

          {/* Sidebar content — always visible on desktop, toggleable on mobile */}
          <div className="sidebar-content">
          <h1 className="viewer-title">{recipe.title}</h1>
          {recipe.description && <p className="viewer-description">{recipe.description}</p>}

          {/* Project status — start/finish + session history */}
          <ProjectStatus recipe={recipe} onUpdated={setRecipe} />

          {recipe.categories.length > 0 && (
            <div className="viewer-meta-group">
              <div className="viewer-meta-label"><FolderOpen size={14} /><span>{t('categories')}</span></div>
              <div className="viewer-meta-pills">
                {recipe.categories.map(cat => (
                  <span key={cat} className="meta-pill category-pill">{cat}</span>
                ))}
              </div>
            </div>
          )}

          {recipe.tags.length > 0 && (
            <div className="viewer-meta-group">
              <div className="viewer-meta-label"><Tag size={14} /><span>{t('tags')}</span></div>
              <div className="viewer-meta-pills">
                {recipe.tags.map(tag => <span key={tag} className="meta-pill">{tag}</span>)}
              </div>
            </div>
          )}

          <p className="viewer-date">
            {t('added')} {new Date(recipe.created_date).toLocaleDateString(
              t('language') === 'no' ? 'nb-NO' : 'en-US',
              { year: 'numeric', month: 'long', day: 'numeric' }
            )}
          </p>
          </div>{/* end sidebar-content */}
        </aside>
      </div>

      {editing && (
        <EditModal t={t} recipe={recipe}
          onClose={() => setEditing(false)}
          onSaved={(updated) => { setRecipe(updated); setEditing(false); }} />
      )}

      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(false)}>
          <div className="confirm-modal" onClick={e => e.stopPropagation()}>
            <h3>{t('deleteConfirmTitle')}</h3>
            <p>{t('deleteConfirmText')} <strong>{recipe.title}</strong> {t('deleteConfirmText2')}</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteConfirm(false)}>{t('cancel')}</button>
              <button className="btn-danger" onClick={handleDelete}>{t('delete')}</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Knitting tools panel (row/stitch/repeat/notes) ── */}
      <KnittingToolbar recipeId={recipeId} t={t} />
    </div>
  );
}

function EditModal({ t, recipe, onClose, onSaved }) {
  const [title, setTitle]           = useState(recipe.title);
  const [description, setDesc]      = useState(recipe.description || '');
  const [categories, setCategories] = useState([]);
  const [selCats, setSelCats]       = useState(recipe.categories);
  const [tagInput, setTagInput]     = useState(recipe.tags.join(', '));
  const [saving, setSaving]         = useState(false);

  useEffect(() => { fetchCategories().then(setCategories).catch(console.error); }, []);

  const toggleCat = (cat) => {
    setSelCats(prev => prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]);
  };

  const handleSave = async () => {
    if (!title.trim()) return alert(t('recipeNameLabel') + ' is required.');
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
      alert('Failed to save.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={onClose}>
      <div className="edit-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{t('editRecipeTitle')}</h3>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>
        <div className="modal-body">
          <label className="form-label">{t('recipeNameLabel')} *</label>
          <input className="form-input" value={title} onChange={e => setTitle(e.target.value)}
            placeholder={t('recipeNamePlaceholder')} />

          <label className="form-label">{t('notesLabel')}</label>
          <textarea className="form-input form-textarea" value={description}
            onChange={e => setDesc(e.target.value)} placeholder={t('notesPlaceholder')} rows={3} />

          <label className="form-label">{t('categoryLabel')}</label>
          <div className="form-pills">
            {categories.map(cat => (
              <button key={cat} type="button"
                className={`pill ${selCats.includes(cat) ? 'pill-active' : ''}`}
                onClick={() => toggleCat(cat)}>{cat}</button>
            ))}
          </div>

          <label className="form-label">
            {t('tagsLabel')} <span className="form-hint">— {t('tagsSeparator')}</span>
          </label>
          <input className="form-input" value={tagInput} onChange={e => setTagInput(e.target.value)}
            placeholder={t('tagsPlaceholder')} />
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>{t('cancel')}</button>
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? t('saving') : t('saveChanges')}
          </button>
        </div>
      </div>
    </div>
  );
}
