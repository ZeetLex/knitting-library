import React, { useRef, useState } from 'react';
import { X, RotateCw, RotateCcw, Trash2, ImagePlus, Scissors, SlidersHorizontal, GripVertical } from 'lucide-react';
import { imageUrl, rotateImage, deleteRecipeImage, cropImage, adjustImage, restoreOriginalImage, addImagesToRecipe, convertImagesToPdf } from '../utils/api';
import CropModal from './CropModal';
import ImageAdjustPanel from './ImageAdjustPanel';
import ReorderModal from './ReorderModal';
import './RepairPdfModal.css';

/**
 * Popup that shows the current source images for a PDF-backed recipe, with
 * the same crop/rotate/reorder/delete/add tools as the main viewer, then
 * re-converts and overwrites the PDF on save.
 *
 * Every edit here is applied to the server immediately (there is no real
 * "cancel"), so onClose reports whether anything changed — the parent must
 * resync its recipe/PDF state if the modal is dismissed without converting.
 *
 * Props: { t, recipeId, recipe, onClose(didEdit), onConverted(result) }
 */
export default function RepairPdfModal({ t, recipeId, recipe, onClose, onConverted }) {
  const [images, setImages] = useState(recipe.images || []);
  const [imageIndex, setImageIndex] = useState(0);
  const [imageVersions, setImageVersions] = useState({});
  const [cropOpen, setCropOpen] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [addingImages, setAddingImages] = useState(false);
  const [converting, setConverting] = useState(false);
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);
  const addInputRef = useRef(null);

  const filename = images[imageIndex];
  const markDirty = (result) => { if (result?.pdf_invalidated) setDirty(true); };

  const handleRotate = async (direction) => {
    if (!filename) return;
    try {
      const result = await rotateImage(recipeId, filename, direction);
      setImageVersions(v => ({ ...v, [filename]: Date.now() }));
      markDirty(result);
    } catch (e) {
      setError(t('convertImagesPdfError'));
    }
  };

  const handleDelete = async () => {
    if (!filename) return;
    try {
      const result = await deleteRecipeImage(recipeId, filename);
      const next = images.filter(img => img !== filename);
      setImages(next);
      setImageIndex(i => Math.min(i, Math.max(0, next.length - 1)));
      setDeleteConfirm(false);
      markDirty(result);
    } catch (e) {
      setError(t('convertImagesPdfError'));
      setDeleteConfirm(false);
    }
  };

  const handleCrop = async (points) => {
    if (!filename) return;
    try {
      const result = await cropImage(recipeId, filename, points);
      setImageVersions(v => ({ ...v, [filename]: Date.now() }));
      setCropOpen(false);
      markDirty(result);
    } catch (e) {
      setError(t('convertImagesPdfError'));
    }
  };

  const handleAdjust = async (adjustments) => {
    if (!filename) return;
    const result = await adjustImage(recipeId, filename, adjustments);
    setImageVersions(v => ({ ...v, [filename]: Date.now() }));
    markDirty(result);
    setAdjustOpen(false);
  };

  const handleRestore = async () => {
    if (!filename) return;
    const result = await restoreOriginalImage(recipeId, filename);
    setImageVersions(v => ({ ...v, [filename]: Date.now() }));
    markDirty(result);
    setAdjustOpen(false);
  };

  const handleAddImages = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setAddingImages(true);
    try {
      const updated = await addImagesToRecipe(recipeId, files);
      setImages(updated.images || []);
      setDirty(true);
    } catch (e) {
      setError(t('addImagesError'));
    } finally {
      setAddingImages(false);
      if (addInputRef.current) addInputRef.current.value = '';
    }
  };

  const handleConvert = async () => {
    setConverting(true); setError('');
    try {
      const result = await convertImagesToPdf(recipeId);
      onConverted(result);
    } catch (e) {
      setError(e.message || t('convertImagesPdfError'));
    } finally {
      setConverting(false);
    }
  };

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={() => onClose(dirty)}>
      <div className="repair-pdf-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{t('repairPdfTitle')}</h3>
          <button className="modal-close" onClick={() => onClose(dirty)}><X size={20} /></button>
        </div>
        <p className="repair-pdf-help">{t('repairPdfHint')}</p>

        {dirty && <p className="status-error repair-pdf-warning">{t('pdfOutOfDate')}</p>}
        {error && <p className="status-error">{error}</p>}

        <div className="repair-pdf-body">
          <div className="repair-pdf-preview">
            {filename && (
              <img src={imageUrl(recipeId, filename, imageVersions[filename])} alt="" />
            )}
          </div>
          <div className="repair-pdf-strip">
            {images.map((img, i) => (
              <button
                key={img}
                type="button"
                className={`repair-pdf-thumb ${i === imageIndex ? 'active' : ''}`}
                onClick={() => setImageIndex(i)}
              >
                <img src={imageUrl(recipeId, img, imageVersions[img])} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        </div>

        <div className="repair-pdf-toolbar">
          <button className="btn-secondary" onClick={() => handleRotate('ccw')} disabled={!filename} title={t('rotateCCW')}>
            <RotateCcw size={16} />
          </button>
          <button className="btn-secondary" onClick={() => handleRotate('cw')} disabled={!filename} title={t('rotateCW')}>
            <RotateCw size={16} />
          </button>
          <button className="btn-secondary" onClick={() => setCropOpen(true)} disabled={!filename}>
            <Scissors size={16} /> {t('cropImage')}
          </button>
          <button className="btn-secondary" onClick={() => setAdjustOpen(true)} disabled={!filename}>
            <SlidersHorizontal size={16} /> {t('adjustImage')}
          </button>
          <button className="btn-secondary" onClick={() => setReordering(true)} disabled={images.length < 2}>
            <GripVertical size={16} /> {t('reorderImages')}
          </button>
          <button className="btn-secondary" onClick={() => setDeleteConfirm(true)} disabled={!filename || images.length < 2} title={t('delete')}>
            <Trash2 size={16} />
          </button>
          <label className="btn-secondary repair-pdf-add">
            <ImagePlus size={16} /> {addingImages ? t('addingImages') : t('addImages')}
            <input ref={addInputRef} type="file" accept="image/*" multiple hidden onChange={handleAddImages} disabled={addingImages} />
          </label>
        </div>

        <div className="modal-footer">
          <button className="btn-secondary" onClick={() => onClose(dirty)}>{t('close')}</button>
          <button className="btn-primary" onClick={handleConvert} disabled={converting || !images.length}>
            {converting ? t('creatingPdf') : t('saveAndConvert')}
          </button>
        </div>

        {deleteConfirm && (
          <div className="modal-overlay" onClick={() => setDeleteConfirm(false)}>
            <div className="confirm-modal" onClick={e => e.stopPropagation()}>
              <h3>{t('deleteImageConfirm')}</h3>
              <p>{t('deleteImageConfirmText')}</p>
              <div className="confirm-actions">
                <button className="btn-secondary" onClick={() => setDeleteConfirm(false)}>{t('cancel')}</button>
                <button className="btn-danger" onClick={handleDelete}>{t('delete')}</button>
              </div>
            </div>
          </div>
        )}

        {cropOpen && filename && (
          <CropModal
            t={t}
            recipeId={recipeId}
            filename={filename}
            imageVersion={imageVersions[filename]}
            onClose={() => setCropOpen(false)}
            onCrop={handleCrop}
          />
        )}

        {adjustOpen && filename && (
          <ImageAdjustPanel
            t={t}
            imageSrc={imageUrl(recipeId, filename, imageVersions[filename])}
            onClose={() => setAdjustOpen(false)}
            onApply={handleAdjust}
            onRestore={handleRestore}
          />
        )}

        {reordering && (
          <ReorderModal
            t={t}
            recipeId={recipeId}
            images={images}
            onClose={() => setReordering(false)}
            onSaved={(newOrder, result) => {
              setImages(newOrder);
              markDirty(result);
              setImageIndex(0);
              setReordering(false);
            }}
          />
        )}
      </div>
    </div>
  );
}
