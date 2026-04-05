import React, { useState, useCallback, useEffect } from 'react';
import { X, UploadCloud, FileText, Image, CheckCircle2, AlertCircle, FolderOpen, AlertTriangle, RotateCcw, RotateCw, Scissors, Trash2, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, GripVertical } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { createRecipe, checkDuplicate, fetchCategories, fetchTags, rotateImage, deleteRecipeImage, cropImage, saveImageOrder, imageUrl } from '../utils/api';
import CropModal from './CropModal';
import './UploadModal.css';

// ── PillInput ─────────────────────────────────────────────────────────────────
function PillInput({ label, hint, values, allOptions, onChange, placeholder }) {
  const [input, setInput] = useState('');
  const filtered = allOptions.filter(
    o => o.toLowerCase().includes(input.toLowerCase()) && !values.includes(o)
  );
  const add = (val) => {
    const v = val.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setInput('');
  };
  const remove = (v) => onChange(values.filter(x => x !== v));

  return (
    <div className="form-field" style={{ position: 'relative' }}>
      <label className="form-label">
        {label}{hint && <span className="form-hint"> — {hint}</span>}
      </label>
      <div className="pill-input-wrap" onClick={e => e.currentTarget.querySelector('input')?.focus()}>
        {values.map(v => (
          <span key={v} className="pill-token">
            {v}
            <button type="button" className="pill-token-x" onClick={() => remove(v)}>×</button>
          </span>
        ))}
        <input
          type="text"
          className="pill-bare-input"
          placeholder={values.length === 0 ? placeholder : ''}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if ((e.key === ' ' || e.key === 'Enter' || e.key === ',') && input.trim()) {
              e.preventDefault(); add(input);
            }
            if (e.key === 'Backspace' && !input && values.length) remove(values[values.length - 1]);
          }}
        />
      </div>
      {input && filtered.length > 0 && (
        <ul className="pill-suggestions">
          {filtered.map(s => <li key={s} onMouseDown={() => add(s)}>{s}</li>)}
        </ul>
      )}
    </div>
  );
}

// ── Image Edit Step ───────────────────────────────────────────────────────────
// Shown after a successful image-type upload so the user can tidy scanned photos
// before the recipe lands in the library.
function ImageEditStep({ t, recipe, onDone }) {
  const [images, setImages]         = useState(recipe.images || []);
  const [index, setIndex]           = useState(0);
  const [versions, setVersions]     = useState({});  // { filename: timestamp }
  const [cropOpen, setCropOpen]     = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [reorderMode, setReorderMode]    = useState(false);
  const recipeId = recipe.id;

  const currentFile = images[index] ?? null;

  // ── Handlers ────────────────────────────────────────────────────────────────
  const bustVersion = (filename) =>
    setVersions(v => ({ ...v, [filename]: Date.now() }));

  const handleRotate = async (direction) => {
    if (!currentFile) return;
    try {
      await rotateImage(recipeId, currentFile, direction);
      bustVersion(currentFile);
    } catch (_) { alert('Could not rotate image.'); }
  };

  const handleDelete = async () => {
    if (!currentFile) return;
    try {
      await deleteRecipeImage(recipeId, currentFile);
      const next = images.filter(img => img !== currentFile);
      setImages(next);
      setIndex(i => Math.min(i, Math.max(0, next.length - 1)));
      setDeleteConfirm(false);
    } catch (_) { alert('Could not delete image.'); setDeleteConfirm(false); }
  };

  const handleCrop = async (points) => {
    if (!currentFile) return;
    try {
      await cropImage(recipeId, currentFile, points);
      bustVersion(currentFile);
      setCropOpen(false);
    } catch (_) { alert('Could not crop image.'); }
  };

  // Reorder: simple up/down swap
  const moveImage = (fromIdx, dir) => {
    const toIdx = fromIdx + dir;
    if (toIdx < 0 || toIdx >= images.length) return;
    const next = [...images];
    [next[fromIdx], next[toIdx]] = [next[toIdx], next[fromIdx]];
    setImages(next);
    if (index === fromIdx) setIndex(toIdx);
    else if (index === toIdx) setIndex(fromIdx);
  };

  const saveReorder = async () => {
    try { await saveImageOrder(recipeId, images); } catch (_) {}
    setReorderMode(false);
  };

  if (images.length === 0) {
    return (
      <div className="upload-edit-step upload-edit-empty">
        <p>All images deleted.</p>
        <button className="btn-primary" onClick={onDone}>Done</button>
      </div>
    );
  }

  return (
    <div className="upload-edit-step">
      {/* ── Header ── */}
      <div className="upload-edit-header">
        <span className="upload-edit-label">
          {t('editImagesStep') || 'Edit images'} · {index + 1}/{images.length}
        </span>
        {images.length > 1 && (
          <button
            className={`upload-edit-reorder-btn ${reorderMode ? 'active' : ''}`}
            onClick={() => reorderMode ? saveReorder() : setReorderMode(true)}
          >
            <GripVertical size={14} />
            {reorderMode ? (t('saveOrder') || 'Save order') : (t('reorderImages') || 'Reorder')}
          </button>
        )}
      </div>

      {/* ── Main image preview ── */}
      <div className="upload-edit-preview">
        {images.length > 1 && (
          <button
            className="upload-edit-nav prev"
            onClick={() => setIndex(i => Math.max(0, i - 1))}
            disabled={index === 0}
          ><ChevronLeft size={24} /></button>
        )}
        <img
          key={`${currentFile}-${versions[currentFile] || 0}`}
          className="upload-edit-img"
          src={imageUrl(recipeId, currentFile, versions[currentFile] || recipe.thumbnail_version)}
          alt={`Image ${index + 1}`}
        />
        {images.length > 1 && (
          <button
            className="upload-edit-nav next"
            onClick={() => setIndex(i => Math.min(images.length - 1, i + 1))}
            disabled={index === images.length - 1}
          ><ChevronRight size={24} /></button>
        )}
      </div>

      {/* ── Action toolbar ── */}
      {!reorderMode && (
        <div className="upload-edit-toolbar">
          <button className="upload-edit-tool" onClick={() => handleRotate('ccw')} title={t('rotateCCW') || 'Rotate left'}>
            <RotateCcw size={18} />
            <span>{t('rotateCCW') || 'Left'}</span>
          </button>
          <button className="upload-edit-tool" onClick={() => handleRotate('cw')} title={t('rotateCW') || 'Rotate right'}>
            <RotateCw size={18} />
            <span>{t('rotateCW') || 'Right'}</span>
          </button>
          <button className="upload-edit-tool" onClick={() => setCropOpen(true)} title={t('cropImage') || 'Crop'}>
            <Scissors size={18} />
            <span>{t('cropImage') || 'Crop'}</span>
          </button>
          <button className="upload-edit-tool upload-edit-tool--danger" onClick={() => setDeleteConfirm(true)} title={t('deleteImage') || 'Delete'}>
            <Trash2 size={18} />
            <span>{t('deleteImage') || 'Delete'}</span>
          </button>
        </div>
      )}

      {/* ── Thumbnail strip / reorder list ── */}
      {images.length > 1 && (
        <div className={`upload-edit-strip ${reorderMode ? 'upload-edit-strip--reorder' : ''}`}>
          {images.map((img, i) => (
            <div key={img} className={`upload-edit-strip-item ${i === index ? 'active' : ''}`}>
              <button
                className="upload-edit-strip-thumb"
                onClick={() => { setIndex(i); }}
              >
                <img
                  src={imageUrl(recipeId, img, versions[img] || recipe.thumbnail_version)}
                  alt={`Image ${i + 1}`}
                  loading="lazy"
                />
                <span className="upload-edit-strip-num">{i + 1}</span>
              </button>
              {reorderMode && (
                <div className="upload-edit-strip-arrows">
                  <button onClick={() => moveImage(i, -1)} disabled={i === 0} title="Move up">
                    <ChevronUp size={13} />
                  </button>
                  <button onClick={() => moveImage(i, 1)} disabled={i === images.length - 1} title="Move down">
                    <ChevronDown size={13} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Footer ── */}
      <div className="upload-edit-footer">
        {reorderMode ? (
          <button className="btn-secondary" onClick={() => setReorderMode(false)}>{t('cancel')}</button>
        ) : (
          <p className="upload-edit-hint">{t('editImagesHint') || 'Rotate or crop scanned images to straighten them, then tap Done.'}</p>
        )}
        {!reorderMode && (
          <button className="btn-primary" onClick={onDone}>{t('done') || 'Done'}</button>
        )}
        {reorderMode && (
          <button className="btn-primary" onClick={saveReorder}>{t('saveOrder') || 'Save order'}</button>
        )}
      </div>

      {/* ── Crop modal ── */}
      {cropOpen && currentFile && (
        <CropModal
          t={t}
          recipeId={recipeId}
          filename={currentFile}
          imageVersion={versions[currentFile] || recipe.thumbnail_version}
          onClose={() => setCropOpen(false)}
          onCrop={handleCrop}
        />
      )}

      {/* ── Delete confirm ── */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(false)}>
          <div className="confirm-modal" onClick={e => e.stopPropagation()}>
            <h3>{t('deleteImageConfirm') || 'Delete this image?'}</h3>
            <p>{t('deleteImageConfirmText') || 'This cannot be undone.'}</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteConfirm(false)}>{t('cancel')}</button>
              <button className="btn-danger" onClick={handleDelete}>{t('delete')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main UploadModal ──────────────────────────────────────────────────────────
export default function UploadModal({ onClose, onSuccess }) {
  const { t } = useApp();
  const [step, setStep]             = useState('form'); // 'form' | 'editing' | 'done'
  const [files, setFiles]           = useState([]);
  const [title, setTitle]           = useState('');
  const [description, setDesc]      = useState('');
  const [selCats, setSelCats]       = useState([]);
  const [selTags, setSelTags]       = useState([]);
  const [allCats, setAllCats]       = useState([]);
  const [allTags, setAllTags]       = useState([]);
  const [dragging, setDragging]     = useState(false);
  const [uploading, setUploading]   = useState(false);
  const [error, setError]           = useState('');
  const [dupWarning, setDupWarning] = useState(null);
  const [uploadedRecipe, setUploadedRecipe] = useState(null);

  useEffect(() => {
    fetchCategories().then(setAllCats).catch(console.error);
    fetchTags().then(setAllTags).catch(console.error);
  }, []);

  const handleFiles = useCallback((newFiles) => {
    const valid = Array.from(newFiles).filter(f =>
      f.type === 'application/pdf' || f.type.startsWith('image/')
    );
    if (valid.length === 0) { setError(t('uploadErrorFormat')); return; }
    setError('');
    setFiles(valid);
    if (!title && valid.length > 0) {
      const name = valid[0].name.replace(/\.[^.]+$/, '').replace(/[-_]/g, ' ');
      setTitle(name.charAt(0).toUpperCase() + name.slice(1));
    }
  }, [title, t]);

  const handleDrop = useCallback((e) => {
    e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const doUpload = async () => {
    setError(''); setUploading(true); setDupWarning(null);
    try {
      const fd = new FormData();
      fd.append('title', title.trim());
      fd.append('description', description.trim());
      fd.append('categories', selCats.join(','));
      fd.append('tags', selTags.join(','));
      files.forEach(f => fd.append('files', f));
      const result = await createRecipe(fd);
      setUploadedRecipe(result);
      // Image recipes → go to edit step; PDFs → success immediately
      if (result.file_type === 'images' && result.images?.length > 0) {
        setStep('editing');
      } else {
        setStep('done');
        setTimeout(onSuccess, 1200);
      }
    } catch (e) {
      setError(e.message || t('uploadFailed'));
      setUploading(false);
    }
  };

  const handleSubmit = async () => {
    if (!files.length) return setError(t('uploadErrorNoFile'));
    if (!title.trim()) return setError(t('uploadErrorNoName'));
    setError('');
    const dupes = await checkDuplicate(files, title.trim());
    if (dupes.content_duplicates.length > 0 || dupes.title_duplicates.length > 0) {
      setDupWarning(dupes);
      return;
    }
    await doUpload();
  };

  const fileType  = files.length > 0 ? (files[0].type === 'application/pdf' ? 'pdf' : 'images') : null;
  const totalSize = files.reduce((s, f) => s + f.size, 0);
  const sizeStr   = totalSize < 1024*1024 ? `${(totalSize/1024).toFixed(0)} KB` : `${(totalSize/1024/1024).toFixed(1)} MB`;

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={step === 'editing' ? undefined : onClose}>
      <div className="upload-modal" onClick={e => e.stopPropagation()}>

        {/* ── Done ── */}
        {step === 'done' && (
          <div className="upload-success">
            <CheckCircle2 size={48} className="success-icon" />
            <h4>{t('recipeAdded')}</h4>
            <p>{t('recipeAddedSub')}</p>
          </div>
        )}

        {/* ── Edit images step ── */}
        {step === 'editing' && uploadedRecipe && (
          <>
            <div className="modal-header">
              <h3>{t('editImagesTitle') || 'Edit images'}</h3>
              <span className="upload-step-badge">step 2 / 2</span>
              <button className="modal-close" onClick={() => { setStep('done'); setTimeout(onSuccess, 300); }}><X size={20} /></button>
            </div>
            <ImageEditStep
              t={t}
              recipe={uploadedRecipe}
              onDone={() => { setStep('done'); setTimeout(onSuccess, 300); }}
            />
          </>
        )}

        {/* ── Upload / form step ── */}
        {step === 'form' && (
          <>
            <div className="modal-header">
              <h3>{t('addRecipeTitle')}</h3>
              <button className="modal-close" onClick={onClose}><X size={20} /></button>
            </div>
            <div className="modal-body">
              <div
                className={`drop-zone ${dragging ? 'dragging' : ''} ${files.length ? 'has-files' : ''}`}
                onDrop={handleDrop}
                onDragOver={e => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
              >
                <input type="file" id="file-input" multiple accept=".pdf,image/jpeg,image/png,image/webp"
                  className="file-input-hidden" onChange={e => handleFiles(e.target.files)} />
                <label htmlFor="file-input" className="drop-zone-label">
                  {files.length === 0 ? (
                    <>
                      <UploadCloud size={40} className="drop-icon" />
                      <p className="drop-title">{t('dropTitle')}</p>
                      <p className="drop-sub">
                        {t('dropSub')}<br />
                        <span className="drop-link">{t('dropClick')}</span>
                      </p>
                    </>
                  ) : (
                    <div className="file-preview">
                      {fileType === 'pdf'
                        ? <FileText size={32} className="file-type-icon pdf" />
                        : <Image size={32} className="file-type-icon img" />}
                      <div className="file-info">
                        <p className="file-name">{files.length === 1 ? files[0].name : `${files.length} images selected`}</p>
                        <p className="file-size">{sizeStr}</p>
                      </div>
                      <button type="button" className="file-remove"
                        onClick={e => { e.preventDefault(); e.stopPropagation(); setFiles([]); }}>
                        <X size={16} />
                      </button>
                    </div>
                  )}
                </label>
                <div className="folder-upload-hint">
                  <input type="file" id="folder-input" webkitdirectory="true" directory="true"
                    className="file-input-hidden" onChange={e => handleFiles(e.target.files)} />
                  <label htmlFor="folder-input" className="folder-btn">
                    <FolderOpen size={14} />
                    {t('uploadFolder')}
                  </label>
                </div>
              </div>

              {dupWarning && (
                <div className="dup-warning">
                  <AlertTriangle size={18} className="dup-icon" />
                  <div className="dup-warning-content">
                    <strong>Possible duplicate detected</strong>
                    {dupWarning.content_duplicates.length > 0 && (
                      <p>Same file content already exists as: <em>{dupWarning.content_duplicates.map(d => d.title).join(', ')}</em></p>
                    )}
                    {dupWarning.title_duplicates.length > 0 && (
                      <p>A recipe with this title already exists: <em>{dupWarning.title_duplicates.map(d => d.title).join(', ')}</em></p>
                    )}
                    <div className="dup-actions">
                      <button className="btn-sm btn-ghost" onClick={() => setDupWarning(null)}>Cancel</button>
                      <button className="btn-sm btn-warning" onClick={doUpload}>Upload Anyway</button>
                    </div>
                  </div>
                </div>
              )}

              {error && (
                <div className="upload-error">
                  <AlertCircle size={16} /><span>{error}</span>
                </div>
              )}

              <div className="form-field">
                <label className="form-label">{t('recipeNameLabel')} *</label>
                <input className="form-input" value={title} onChange={e => setTitle(e.target.value)}
                  placeholder={t('recipeNamePlaceholder')} autoFocus />
              </div>

              <div className="form-field">
                <label className="form-label">
                  {t('notesLabel')} <span className="form-hint">— {t('notesOptional')}</span>
                </label>
                <textarea className="form-input form-textarea" value={description}
                  onChange={e => setDesc(e.target.value)} placeholder={t('notesPlaceholder')} rows={2} />
              </div>

              <PillInput
                label={t('categoryLabel')}
                values={selCats}
                allOptions={allCats}
                onChange={setSelCats}
                placeholder="Add a category…"
              />

              <PillInput
                label={t('tagsLabel')}
                hint="space or enter to add"
                values={selTags}
                allOptions={allTags}
                onChange={setSelTags}
                placeholder="Add a tag…"
              />

              {fileType === 'images' && files.length > 0 && (
                <p className="upload-edit-preview-notice">
                  <Scissors size={12} /> After uploading you can crop, rotate, or reorder images.
                </p>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={onClose} disabled={uploading}>{t('cancel')}</button>
              <button className="btn-primary" onClick={handleSubmit}
                disabled={uploading || !files.length || !title.trim()}>
                {uploading ? <><span className="btn-spinner" /> {t('uploading')}</> : t('addToLibrary')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
