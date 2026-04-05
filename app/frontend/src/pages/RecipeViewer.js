import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, ZoomIn, ZoomOut, Maximize2, Pencil, Trash2, Tag, FolderOpen, X, Image as LucideImage, Download, GripVertical, RotateCw, RotateCcw, Info, Wrench, Scissors } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchRecipe, deleteRecipe, updateRecipe, fetchCategories, pdfUrl, imageUrl, fetchPdfPages, convertPdf, pdfPageUrl, setThumbnail, thumbnailUrl, downloadUrl, saveImageOrder, rotateImage, deleteRecipeImage, cropImage } from '../utils/api';
import { ImageAnnotationCanvas } from '../components/AnnotationCanvas';
import ProjectStatus from '../components/ProjectStatus';
import KnittingToolbar from '../components/KnittingToolbar';
import CropModal from '../components/CropModal';
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
  const [thumbSet, setThumbSet]         = useState(null);  // filename of last set thumbnail
  const [thumbCacheBust, setThumbCacheBust] = useState(null); // timestamp to force browser re-fetch
  const [reordering, setReordering]     = useState(false);
  const [imageVersions, setImageVersions] = useState({}); // { filename: timestamp } for cache-busting after rotate
  const [deleteImageConfirm, setDeleteImageConfirm] = useState(false);
  const [cropOpen, setCropOpen] = useState(false);
  // Controls panel: open by default on desktop, closed on mobile
  const [controlsOpen, setControlsOpen] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 641 : true
  );
  // Mobile bottom tab bar: null = closed, 'images' | 'info' | 'tools' = open panel
  const [mobileTab, setMobileTab] = useState(null);
  const touchStartX = useRef(null);

  const handleSetThumbnail = async (source, filename) => {
    try {
      const result = await setThumbnail(recipeId, source, filename);
      // Update the recipe's thumbnail_version in local state so the sidebar
      // cover preview re-fetches immediately without needing a page reload.
      if (result.thumbnail_version !== undefined) {
        setRecipe(r => ({ ...r, thumbnail_version: result.thumbnail_version }));
      }
      setThumbCacheBust(Date.now());
      setThumbSet(filename);
      setTimeout(() => setThumbSet(null), 2500);
    } catch (e) {
      alert('Could not update cover image.');
    }
  };

  const handleRotate = async (direction) => {
    const filename = recipe?.images?.[imageIndex];
    if (!filename) return;
    try {
      const result = await rotateImage(recipeId, filename, direction);
      // Bust the image cache for this file so the viewer reloads it
      setImageVersions(v => ({ ...v, [filename]: Date.now() }));
      // Update thumbnail_version if the thumbnail was regenerated
      if (result.thumbnail_version !== undefined) {
        setRecipe(r => ({ ...r, thumbnail_version: result.thumbnail_version }));
        setThumbCacheBust(Date.now());
      }
    } catch (e) {
      alert('Could not rotate image.');
    }
  };

  const handleDeleteImage = async () => {
    const filename = recipe?.images?.[imageIndex];
    if (!filename) return;
    try {
      const result = await deleteRecipeImage(recipeId, filename);
      const newImages = recipe.images.filter(img => img !== filename);
      setRecipe(r => ({ ...r, images: newImages }));
      setImageIndex(i => Math.min(i, Math.max(0, newImages.length - 1)));
      setDeleteImageConfirm(false);
      if (result.thumbnail_version !== undefined) {
        setRecipe(r => ({ ...r, thumbnail_version: result.thumbnail_version }));
        setThumbCacheBust(Date.now());
      }
    } catch (e) {
      alert('Could not delete image.');
      setDeleteImageConfirm(false);
    }
  };

  const handleCrop = async (points) => {
    const filename = recipe?.images?.[imageIndex];
    if (!filename) return;
    try {
      const result = await cropImage(recipeId, filename, points);
      setImageVersions(v => ({ ...v, [filename]: Date.now() }));
      setCropOpen(false);
      if (result.thumbnail_version !== undefined) {
        setRecipe(r => ({ ...r, thumbnail_version: result.thumbnail_version }));
        setThumbCacheBust(Date.now());
      }
    } catch (e) {
      alert('Could not crop image.');
    }
  };

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
          <a
            className="viewer-action-btn"
            href={downloadUrl(recipeId)}
            download
            title={recipe?.file_type === 'pdf' ? 'Download PDF' : 'Download images (ZIP)'}
          >
            <Download size={18} />
          </a>
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
                      <div className="pdf-page-number">
                        {t('pdfPage')} {i + 1}
                        <button
                          className={`set-cover-btn ${thumbSet === page ? 'set-cover-btn--done' : ''}`}
                          onClick={() => handleSetThumbnail('pdf_page', page)}
                          title="Use this page as the cover image"
                        >
                          <LucideImage size={13} />
                          <span>{thumbSet === page ? '✓ Cover set!' : 'Set as cover'}</span>
                        </button>
                      </div>
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
                    src={imageUrl(recipeId, recipe.images[imageIndex], imageVersions[recipe.images[imageIndex]] || recipe.thumbnail_version)}
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

              {/* ── Controls toggle handle ── */}
              <button
                className="controls-toggle"
                onClick={() => setControlsOpen(o => !o)}
                aria-label={controlsOpen ? 'Hide controls' : 'Show controls'}
              >
                <span className="controls-toggle-track" />
                {controlsOpen ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
              </button>

              {/* ── Collapsible controls panel ── */}
              <div className={`image-controls-wrap ${controlsOpen ? 'controls-open' : ''}`}>
                <div className="image-controls">
                  <button onClick={() => setZoom(z => Math.max(0.5, z-0.25))}><ZoomOut size={16} /></button>
                  <button onClick={() => setZoom(1)}>{t('resetZoom')}</button>
                  <button onClick={() => setZoom(z => Math.min(4, z+0.25))}><ZoomIn size={16} /></button>
                  <button onClick={() => { setFullscreen(f => !f); setZoom(1); }}><Maximize2 size={16} /></button>
                  {fullscreen && <button onClick={() => setFullscreen(false)}><X size={16} /></button>}
                  {recipe.images.length > 0 && (
                    <>
                      <button onClick={() => handleRotate('ccw')} title={t('rotateCCW')}>
                        <RotateCcw size={15} />
                      </button>
                      <button onClick={() => handleRotate('cw')} title={t('rotateCW')}>
                        <RotateCw size={15} />
                      </button>
                      <button onClick={() => setCropOpen(true)} title={t('cropImage')}>
                        <Scissors size={14} />
                        <span>{t('cropImage')}</span>
                      </button>
                      <button
                        className={`set-cover-btn ${thumbSet === recipe.images[imageIndex] ? 'set-cover-btn--done' : ''}`}
                        onClick={() => handleSetThumbnail('image', recipe.images[imageIndex])}
                        title="Use this image as the cover"
                      >
                        <LucideImage size={14} />
                        <span>{thumbSet === recipe.images[imageIndex] ? '✓ Cover set!' : 'Set as cover'}</span>
                      </button>
                      <button
                        className="delete-image-btn"
                        onClick={() => setDeleteImageConfirm(true)}
                        title={t('deleteImage')}
                      >
                        <Trash2 size={14} />
                        <span>{t('deleteImage')}</span>
                      </button>
                    </>
                  )}
                  {recipe.images.length > 1 && (
                    <button
                      className="reorder-trigger-btn"
                      onClick={() => setReordering(true)}
                      title={t('reorderImages')}
                    >
                      <GripVertical size={14} />
                      <span>{t('reorderImages')}</span>
                    </button>
                  )}
                </div>
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
                      <img src={imageUrl(recipeId, img, imageVersions[img] || recipe.thumbnail_version)} alt={`${t('pdfPage')} ${i+1}`} loading="lazy" />
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

          {/* Sidebar content — always visible on desktop, hidden on mobile (replaced by mobile tab bar) */}
          <div className="sidebar-content">
            <SidebarInfoContent
              recipe={recipe}
              recipeId={recipeId}
              thumbCacheBust={thumbCacheBust}
              thumbSet={thumbSet}
              onUpdated={setRecipe}
            />
          </div>{/* end sidebar-content */}
        </aside>
      </div>

      {editing && (
        <EditModal t={t} recipe={recipe}
          onClose={() => setEditing(false)}
          onSaved={(updated) => { setRecipe(updated); setEditing(false); }} />
      )}

      {reordering && (
        <ReorderModal
          t={t}
          recipeId={recipeId}
          images={recipe.images}
          onClose={() => setReordering(false)}
          onSaved={(newOrder) => {
            setRecipe(r => ({ ...r, images: newOrder }));
            setImageIndex(0);
            setReordering(false);
          }}
        />
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

      {deleteImageConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteImageConfirm(false)}>
          <div className="confirm-modal" onClick={e => e.stopPropagation()}>
            <h3>{t('deleteImageConfirm')}</h3>
            <p>{t('deleteImageConfirmText')}</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteImageConfirm(false)}>{t('cancel')}</button>
              <button className="btn-danger" onClick={handleDeleteImage}>{t('delete')}</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Perspective crop modal ── */}
      {cropOpen && recipe?.file_type === 'images' && recipe.images.length > 0 && (
        <CropModal
          t={t}
          recipeId={recipeId}
          filename={recipe.images[imageIndex]}
          imageVersion={imageVersions[recipe.images[imageIndex]]}
          onClose={() => setCropOpen(false)}
          onCrop={handleCrop}
        />
      )}

      {/* ── Knitting tools panel — controlled by mobile tab bar on small screens ── */}
      <KnittingToolbar
        recipeId={recipeId}
        t={t}
        mobileOpen={mobileTab === 'tools' ? true : (mobileTab !== null ? false : undefined)}
        onMobileClose={() => setMobileTab(null)}
      />

      {/* ══ Mobile bottom tab bar — hidden on desktop via CSS ══ */}
      <div className="mobile-tab-bar">
        {recipe.file_type === 'images' && (
          <button
            className={`mobile-tab-btn ${mobileTab === 'images' ? 'mobile-tab-btn--active' : ''}`}
            onClick={() => setMobileTab(prev => prev === 'images' ? null : 'images')}
          >
            <LucideImage size={18} />
            <span>{t('mobileTabImages') || 'Images'}</span>
          </button>
        )}
        <button
          className={`mobile-tab-btn ${mobileTab === 'info' ? 'mobile-tab-btn--active' : ''}`}
          onClick={() => setMobileTab(prev => prev === 'info' ? null : 'info')}
        >
          <Info size={18} />
          <span>{t('mobileTabInfo') || 'Info'}</span>
        </button>
        <button
          className={`mobile-tab-btn ${mobileTab === 'tools' ? 'mobile-tab-btn--active' : ''}`}
          onClick={() => setMobileTab(prev => prev === 'tools' ? null : 'tools')}
        >
          <Wrench size={18} />
          <span>{t('mobileTabTools') || 'Tools'}</span>
        </button>
      </div>

      {/* ── Mobile Images panel ── */}
      {recipe.file_type === 'images' && (
        <div className={`mobile-panel mobile-panel--images ${mobileTab === 'images' ? 'mobile-panel--open' : ''}`}>
          <button className="mobile-panel-handle" onClick={() => setMobileTab(null)} aria-label="Close panel">
            <span className="mobile-panel-pill" />
          </button>
          <div className="mobile-panel-body">
            {/* Thumbnail strip */}
            {recipe.images.length > 1 && (
              <div className="image-strip mobile-image-strip">
                {recipe.images.map((img, i) => (
                  <button key={img} className={`strip-thumb ${i === imageIndex ? 'active' : ''}`}
                    onClick={() => setImageIndex(i)}>
                    <img src={imageUrl(recipeId, img, imageVersions[img] || recipe.thumbnail_version)} alt={`Page ${i + 1}`} loading="lazy" />
                  </button>
                ))}
              </div>
            )}
            {/* Image action buttons */}
            <div className="mobile-image-actions">
              <button onClick={() => setZoom(z => Math.max(0.5, z - 0.25))}>
                <ZoomOut size={20} /><span>{t('zoomOut') || '−'}</span>
              </button>
              <button onClick={() => setZoom(1)}>
                <span>{t('resetZoom') || 'Reset'}</span>
              </button>
              <button onClick={() => setZoom(z => Math.min(4, z + 0.25))}>
                <ZoomIn size={20} /><span>{t('zoomIn') || '+'}</span>
              </button>
              <button onClick={() => { setFullscreen(f => !f); setZoom(1); }}>
                <Maximize2 size={20} /><span>{fullscreen ? (t('exitFullscreen') || 'Exit') : (t('openFull') || 'Full')}</span>
              </button>
              {recipe.images.length > 0 && (
                <>
                  <button onClick={() => handleRotate('ccw')}>
                    <RotateCcw size={20} /><span>{t('rotateCCW') || '↺'}</span>
                  </button>
                  <button onClick={() => handleRotate('cw')}>
                    <RotateCw size={20} /><span>{t('rotateCW') || '↻'}</span>
                  </button>
                  <button onClick={() => { setCropOpen(true); setMobileTab(null); }}>
                    <Scissors size={20} /><span>{t('cropImage') || 'Crop'}</span>
                  </button>
                  <button onClick={() => handleSetThumbnail('image', recipe.images[imageIndex])}>
                    <LucideImage size={20} /><span>Cover</span>
                  </button>
                  <button className="mobile-action-btn--danger" onClick={() => setDeleteImageConfirm(true)}>
                    <Trash2 size={20} /><span>{t('deleteImage') || 'Delete'}</span>
                  </button>
                </>
              )}
              {recipe.images.length > 1 && (
                <button onClick={() => setReordering(true)}>
                  <GripVertical size={20} /><span>{t('reorderImages') || 'Reorder'}</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Mobile Info panel ── */}
      <div className={`mobile-panel mobile-panel--info ${mobileTab === 'info' ? 'mobile-panel--open' : ''}`}>
        <button className="mobile-panel-handle" onClick={() => setMobileTab(null)} aria-label="Close panel">
          <span className="mobile-panel-pill" />
        </button>
        <div className="mobile-panel-body">
          {recipe && (
            <SidebarInfoContent
              recipe={recipe}
              recipeId={recipeId}
              thumbCacheBust={thumbCacheBust}
              thumbSet={thumbSet}
              onUpdated={setRecipe}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Sidebar info content — shared between desktop sidebar and mobile Info panel ── */
function SidebarInfoContent({ recipe, recipeId, thumbCacheBust, thumbSet, onUpdated }) {
  const { t } = useApp();
  return (
    <>
      <div className="viewer-cover-wrap">
        <img
          key={thumbCacheBust || recipe.thumbnail_version || 'initial'}
          className="viewer-cover-thumb"
          src={thumbnailUrl(recipeId, thumbCacheBust || recipe.thumbnail_version)}
          alt="Cover"
        />
        {thumbSet && <div className="viewer-cover-badge">✓ Cover updated!</div>}
      </div>

      <h1 className="viewer-title">{recipe.title}</h1>
      {recipe.description && <p className="viewer-description">{recipe.description}</p>}

      <ProjectStatus recipe={recipe} onUpdated={onUpdated} />

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
    </>
  );
}

function EditModal({ t, recipe, onClose, onSaved }) {
  const [title, setTitle]           = useState(recipe.title);
  const [description, setDesc]      = useState(recipe.description || '');
  const [categories, setCategories] = useState([]);
  const [selCats, setSelCats]       = useState(recipe.categories);
  const [newCatInput, setNewCatInput] = useState('');
  const [tagInput, setTagInput]     = useState(recipe.tags.join(', '));
  const [saving, setSaving]         = useState(false);

  useEffect(() => { fetchCategories().then(setCategories).catch(console.error); }, []);

  const toggleCat = (cat) => {
    setSelCats(prev => prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]);
  };

  const addNewCategory = () => {
    const cat = newCatInput.trim();
    if (cat && !categories.includes(cat) && !selCats.includes(cat)) {
      setCategories(prev => [...prev, cat]);
      setNewCatInput('');
    }
  };

  const removeCategory = (cat) => {
    // Only remove from existing categories, not from selected
    if (!selCats.includes(cat)) {
      setCategories(prev => prev.filter(c => c !== cat));
    }
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
          <div className="category-editor">
            {/* Existing categories - can be toggled or deleted */}
            <div className="form-pills">
              {categories.map(cat => (
                <div key={cat} className="pill-group">
                  <button type="button"
                    className={`pill ${selCats.includes(cat) ? 'pill-active' : ''}`}
                    onClick={() => toggleCat(cat)}>{cat}</button>
                  <button type="button" className="pill-remove" onClick={() => removeCategory(cat)}>×</button>
                </div>
              ))}
            </div>

            {/* Add new category input */}
            <div className="add-category-row">
              <input
                type="text"
                className="add-category-input"
                value={newCatInput}
                onChange={e => setNewCatInput(e.target.value)}
                placeholder={t('newCategoryPlaceholder')}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    addNewCategory();
                  }
                }}
              />
              <button type="button" className="add-category-btn" onClick={addNewCategory}>
                +
              </button>
            </div>
            <p className="category-hint">{t('categoryHint')}</p>
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

function ReorderModal({ t, recipeId, images, onClose, onSaved }) {
  const [order, setOrder]           = useState([...images]);
  const [dragIdx, setDragIdx]       = useState(null);   // which row is being dragged
  const [dropIdx, setDropIdx]       = useState(null);   // which row the drag is over
  const [saving, setSaving]         = useState(false);
  const [saved, setSaved]           = useState(false);

  const moveItem = (idx, dir) => {
    const target = idx + dir;
    if (target < 0 || target >= order.length) return;
    const next = [...order];
    [next[idx], next[target]] = [next[target], next[idx]];
    setOrder(next);
  };

  const handleDragStart = (e, i) => {
    // Store the source index both in state and in dataTransfer as a fallback
    setDragIdx(i);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(i));
  };

  const handleDragOver = (e, i) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dropIdx !== i) setDropIdx(i);
  };

  // Only commit the reorder on drop — avoids re-render mid-drag breaking the drag
  const handleDrop = (e, i) => {
    e.preventDefault();
    const from = dragIdx ?? parseInt(e.dataTransfer.getData('text/plain'), 10);
    setDragIdx(null);
    setDropIdx(null);
    if (isNaN(from) || from === i) return;
    const next = [...order];
    const [moved] = next.splice(from, 1);
    next.splice(i, 0, moved);
    setOrder(next);
  };

  const handleDragEnd = () => { setDragIdx(null); setDropIdx(null); };

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveImageOrder(recipeId, order);
      setSaved(true);
      setTimeout(() => onSaved(order), 700);
    } catch (e) {
      alert('Failed to save order.');
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={onClose}>
      <div className="reorder-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{t('reorderTitle')}</h3>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>
        <p className="reorder-help">{t('reorderHelp')}</p>
        <div className="reorder-list">
          {order.map((img, i) => (
            <div
              key={img}
              className={`reorder-item${
                dragIdx === i  ? ' reorder-item--dragging'    :
                dropIdx  === i ? ' reorder-item--drop-target' : ''
              }`}
              draggable
              onDragStart={e => handleDragStart(e, i)}
              onDragOver={e  => handleDragOver(e, i)}
              onDrop={e      => handleDrop(e, i)}
              onDragLeave={() => setDropIdx(null)}
              onDragEnd={handleDragEnd}
            >
              <GripVertical size={18} className="reorder-grip" />
              <span className="reorder-num">{i + 1}</span>
              <img
                className="reorder-thumb"
                src={imageUrl(recipeId, img)}
                alt={`Image ${i + 1}`}
                loading="lazy"
                draggable={false}
              />
              <span className="reorder-name">{img}</span>
              <div className="reorder-arrows">
                <button
                  className="reorder-arrow"
                  onClick={() => moveItem(i, -1)}
                  disabled={i === 0}
                  title="Move up"
                ><ChevronUp size={15} /></button>
                <button
                  className="reorder-arrow"
                  onClick={() => moveItem(i, 1)}
                  disabled={i === order.length - 1}
                  title="Move down"
                ><ChevronDown size={15} /></button>
              </div>
            </div>
          ))}
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose} disabled={saving}>{t('cancel')}</button>
          <button className="btn-primary" onClick={handleSave} disabled={saving || saved}>
            {saved ? t('orderSaved') : saving ? '…' : t('saveOrder')}
          </button>
        </div>
      </div>
    </div>
  );
}

