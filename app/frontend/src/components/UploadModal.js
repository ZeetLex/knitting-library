import React, { useState, useCallback, useEffect } from 'react';
import { X, UploadCloud, FileText, Image, CheckCircle2, AlertCircle, FolderOpen, AlertTriangle } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { createRecipe, checkDuplicate, fetchCategories, fetchTags } from '../utils/api';
import './UploadModal.css';

// ── PillInput — type and press Space/Enter/comma to add a tag pill ────────────
// Works for both categories and tags. Shows a suggestion dropdown of existing
// values so the user can pick one rather than re-typing it.
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
            // Space, Enter, or comma all confirm the current word as a pill
            if ((e.key === ' ' || e.key === 'Enter' || e.key === ',') && input.trim()) {
              e.preventDefault();
              add(input);
            }
            // Backspace on empty input removes the last pill
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

export default function UploadModal({ onClose, onSuccess }) {
  const { t } = useApp();
  const [files, setFiles]           = useState([]);
  const [title, setTitle]           = useState('');
  const [description, setDesc]      = useState('');
  const [selCats, setSelCats]       = useState([]);   // selected category pills
  const [selTags, setSelTags]       = useState([]);   // selected tag pills
  const [allCats, setAllCats]       = useState([]);   // existing categories for suggestions
  const [allTags, setAllTags]       = useState([]);   // existing tags for suggestions
  const [dragging, setDragging]     = useState(false);
  const [uploading, setUploading]   = useState(false);
  const [error, setError]           = useState('');
  const [success, setSuccess]       = useState(false);
  const [dupWarning, setDupWarning] = useState(null);

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
      await createRecipe(fd);
      setSuccess(true);
      setTimeout(onSuccess, 1200);
    } catch (e) {
      setError(e.message || t('uploadFailed'));
      setUploading(false);
    }
  };

  const handleSubmit = async () => {
    if (!files.length) return setError(t('uploadErrorNoFile'));
    if (!title.trim()) return setError(t('uploadErrorNoName'));
    setError('');
    // Run duplicate check first
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
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={onClose}>
      <div className="upload-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{t('addRecipeTitle')}</h3>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>

        {success ? (
          <div className="upload-success">
            <CheckCircle2 size={48} className="success-icon" />
            <h4>{t('recipeAdded')}</h4>
            <p>{t('recipeAddedSub')}</p>
          </div>
        ) : (
          <>
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
