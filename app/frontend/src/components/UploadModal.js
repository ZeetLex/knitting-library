/**
 * UploadModal.js
 * The upload form for adding new recipes.
 * Supports drag-and-drop or click-to-select for PDFs and images.
 * Includes fields for recipe name, categories, and tags.
 */

import React, { useState, useCallback, useEffect } from 'react';
import { X, UploadCloud, FileText, Image, CheckCircle2, AlertCircle, FolderOpen } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { createRecipe, fetchCategories } from '../utils/api';
import './UploadModal.css';

export default function UploadModal({ onClose, onSuccess }) {
  const [files, setFiles]         = useState([]);
  const [title, setTitle]         = useState('');
  const [description, setDesc]    = useState('');
  const [categories, setCategories] = useState([]);
  const [selCats, setSelCats]     = useState([]);
  const [tagInput, setTagInput]   = useState('');
  const [dragging, setDragging]   = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError]         = useState('');
  const [success, setSuccess]     = useState(false);

  // Load available categories when the modal opens
  useEffect(() => {
    fetchCategories().then(setCategories).catch(console.error);
  }, []);

  // Handle files being dropped or selected
  const handleFiles = useCallback((newFiles) => {
    const valid = Array.from(newFiles).filter(f =>
      f.type === 'application/pdf' ||
      f.type.startsWith('image/')
    );
    if (valid.length === 0) {
      setError('Only PDF and image files (JPG, PNG, WebP) are supported.');
      return;
    }
    setError('');
    setFiles(valid);

    // Auto-fill the title from the filename if it's empty
    if (!title && valid.length > 0) {
      const name = valid[0].name.replace(/\.[^.]+$/, '').replace(/[-_]/g, ' ');
      setTitle(name.charAt(0).toUpperCase() + name.slice(1));
    }
  }, [title]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const handleDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const handleDragLeave = () => setDragging(false);

  const toggleCat = (cat) => {
    setSelCats(prev => prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]);
  };

  const handleSubmit = async () => {
    if (!files.length) return setError('Please select at least one file.');
    if (!title.trim()) return setError('Please enter a recipe name.');

    setError('');
    setUploading(true);

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
      setError(e.message || 'Upload failed. Please try again.');
      setUploading(false);
    }
  };

  // Determine what type of files are being uploaded
  const fileType = files.length > 0
    ? (files[0].type === 'application/pdf' ? 'pdf' : 'images')
    : null;

  const totalSize = files.reduce((sum, f) => sum + f.size, 0);
  const sizeStr = totalSize < 1024 * 1024
    ? `${(totalSize / 1024).toFixed(0)} KB`
    : `${(totalSize / 1024 / 1024).toFixed(1)} MB`;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="upload-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <h3>Add Recipe</h3>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>

        {success ? (
          /* Success State */
          <div className="upload-success">
            <CheckCircle2 size={48} className="success-icon" />
            <h4>Recipe Added!</h4>
            <p>Your recipe has been saved to the library.</p>
          </div>
        ) : (
          <>
            <div className="modal-body">
              {/* ─── Drop Zone ──────────────────────────────────────────── */}
              <div
                className={`drop-zone ${dragging ? 'dragging' : ''} ${files.length ? 'has-files' : ''}`}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
              >
                <input
                  type="file"
                  id="file-input"
                  multiple
                  accept=".pdf,image/jpeg,image/png,image/webp"
                  className="file-input-hidden"
                  onChange={e => handleFiles(e.target.files)}
                />
                <label htmlFor="file-input" className="drop-zone-label">
                  {files.length === 0 ? (
                    <>
                      <UploadCloud size={40} className="drop-icon" />
                      <p className="drop-title">Drop your recipe here</p>
                      <p className="drop-sub">
                        PDF, JPG, PNG, or WebP · Single or multiple images<br />
                        <span className="drop-link">Click to browse files</span>
                      </p>
                    </>
                  ) : (
                    <div className="file-preview">
                      {fileType === 'pdf' ? (
                        <FileText size={32} className="file-type-icon pdf" />
                      ) : (
                        <Image size={32} className="file-type-icon img" />
                      )}
                      <div className="file-info">
                        <p className="file-name">
                          {files.length === 1 ? files[0].name : `${files.length} images selected`}
                        </p>
                        <p className="file-size">{sizeStr}</p>
                      </div>
                      <button
                        type="button"
                        className="file-remove"
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setFiles([]); }}
                        aria-label="Remove files"
                      >
                        <X size={16} />
                      </button>
                    </div>
                  )}
                </label>

                {/* Folder upload option */}
                <div className="folder-upload-hint">
                  <input
                    type="file"
                    id="folder-input"
                    webkitdirectory="true"
                    directory="true"
                    className="file-input-hidden"
                    onChange={e => handleFiles(e.target.files)}
                  />
                  <label htmlFor="folder-input" className="folder-btn">
                    <FolderOpen size={14} />
                    Upload entire folder
                  </label>
                </div>
              </div>

              {/* Error message */}
              {error && (
                <div className="upload-error">
                  <AlertCircle size={16} />
                  <span>{error}</span>
                </div>
              )}

              {/* ─── Recipe Name ────────────────────────────────────────── */}
              <div className="form-field">
                <label className="form-label">Recipe Name *</label>
                <input
                  className="form-input"
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="e.g. Cozy Cable Socks"
                  autoFocus
                />
              </div>

              {/* ─── Notes ──────────────────────────────────────────────── */}
              <div className="form-field">
                <label className="form-label">
                  Notes
                  <span className="form-hint"> — optional</span>
                </label>
                <textarea
                  className="form-input form-textarea"
                  value={description}
                  onChange={e => setDesc(e.target.value)}
                  placeholder="Any notes about this pattern…"
                  rows={2}
                />
              </div>

              {/* ─── Categories ─────────────────────────────────────────── */}
              <div className="form-field">
                <label className="form-label">Category</label>
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
              </div>

              {/* ─── Tags ───────────────────────────────────────────────── */}
              <div className="form-field">
                <label className="form-label">
                  Tags
                  <span className="form-hint"> — separate with commas</span>
                </label>
                <input
                  className="form-input"
                  value={tagInput}
                  onChange={e => setTagInput(e.target.value)}
                  placeholder="e.g. wool, fingering weight, easy, DK, stranded"
                />
                <p className="field-hint">
                  Tags can include yarn type, weight, difficulty, designer, needle size, etc.
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="modal-footer">
              <button className="btn-secondary" onClick={onClose} disabled={uploading}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleSubmit}
                disabled={uploading || !files.length || !title.trim()}
              >
                {uploading ? (
                  <><span className="btn-spinner" /> Uploading…</>
                ) : (
                  'Add to Library'
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
