import React, { useState, useCallback, useEffect } from 'react';
import { X, UploadCloud, FileText, Image, CheckCircle2, AlertCircle, FolderOpen } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { createRecipe, fetchCategories } from '../utils/api';
import './UploadModal.css';

export default function UploadModal({ onClose, onSuccess }) {
  const { t } = useApp();
  const [files, setFiles]           = useState([]);
  const [title, setTitle]           = useState('');
  const [description, setDesc]      = useState('');
  const [categories, setCategories] = useState([]);
  const [selCats, setSelCats]       = useState([]);
  const [tagInput, setTagInput]     = useState('');
  const [dragging, setDragging]     = useState(false);
  const [uploading, setUploading]   = useState(false);
  const [error, setError]           = useState('');
  const [success, setSuccess]       = useState(false);

  useEffect(() => {
    fetchCategories().then(setCategories).catch(console.error);
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

  const toggleCat = (cat) => {
    setSelCats(prev => prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]);
  };

  const handleSubmit = async () => {
    if (!files.length) return setError(t('uploadErrorNoFile'));
    if (!title.trim()) return setError(t('uploadErrorNoName'));
    setError(''); setUploading(true);
    try {
      const fd = new FormData();
      fd.append('title', title.trim());
      fd.append('description', description.trim());
      fd.append('categories', selCats.join(','));
      fd.append('tags', tagInput);
      files.forEach(f => fd.append('files', f));
      await createRecipe(fd);
      setSuccess(true);
      setTimeout(onSuccess, 1200);
    } catch (e) {
      setError(e.message || t('uploadFailed'));
      setUploading(false);
    }
  };

  const fileType  = files.length > 0 ? (files[0].type === 'application/pdf' ? 'pdf' : 'images') : null;
  const totalSize = files.reduce((s, f) => s + f.size, 0);
  const sizeStr   = totalSize < 1024*1024 ? `${(totalSize/1024).toFixed(0)} KB` : `${(totalSize/1024/1024).toFixed(1)} MB`;

  return (
    <div className="modal-overlay" onClick={onClose}>
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

              <div className="form-field">
                <label className="form-label">{t('categoryLabel')}</label>
                <div className="form-pills">
                  {categories.map(cat => (
                    <button key={cat} type="button"
                      className={`pill ${selCats.includes(cat) ? 'pill-active' : ''}`}
                      onClick={() => toggleCat(cat)}>
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              <div className="form-field">
                <label className="form-label">
                  {t('tagsLabel')} <span className="form-hint">— {t('tagsSeparator')}</span>
                </label>
                <input className="form-input" value={tagInput}
                  onChange={e => setTagInput(e.target.value)} placeholder={t('tagsPlaceholder')} />
              </div>
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
