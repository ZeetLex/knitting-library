/**
 * YarnUploadModal.js
 * Modal for adding or editing a yarn entry.
 * Supports image upload, all yarn fields, and edit mode.
 */

import React, { useState, useRef, useEffect } from 'react';
import { X, Upload, ImagePlus } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { createYarn, updateYarn, yarnImageUrl } from '../utils/api';
import './YarnUploadModal.css';

const EMPTY = {
  name: '', colour: '', wool_type: '', yardage: '', needles: '',
  tension: '', origin: '', seller: '', price_per_skein: '', product_info: '',
};

export default function YarnUploadModal({ onClose, onSuccess, editYarn }) {
  const { t } = useApp();
  const isEdit = !!editYarn;

  const [fields, setFields]       = useState(isEdit ? { ...editYarn } : { ...EMPTY });
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(isEdit && editYarn.image_path ? yarnImageUrl(editYarn.id) : null);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState('');
  const [dragOver, setDragOver]   = useState(false);
  const fileRef = useRef();

  // Close on Escape
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  const set = (k, v) => setFields(f => ({ ...f, [k]: v }));

  const handleImage = (file) => {
    if (!file) return;
    setImageFile(file);
    setImagePreview(URL.createObjectURL(file));
  };

  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith('image/')) handleImage(f);
  };

  const handleSubmit = async () => {
    if (!fields.name.trim()) { setError(t('yarnName') + ' is required'); return; }
    setSaving(true); setError('');
    try {
      const fd = new FormData();
      Object.entries(fields).forEach(([k, v]) => {
        if (k !== 'id' && k !== 'created_date' && k !== 'image_path') fd.append(k, v);
      });
      if (imageFile) fd.append('image', imageFile);
      const result = isEdit ? await updateYarn(editYarn.id, fd) : await createYarn(fd);
      onSuccess(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="yum-modal">
        {/* Header */}
        <div className="yum-header">
          <h2 className="yum-title">{isEdit ? t('editYarn') : t('addYarn')}</h2>
          <button className="yum-close" onClick={onClose}><X size={20} /></button>
        </div>

        <div className="yum-body">
          {/* Image upload */}
          <div
            className={`yum-image-drop ${dragOver ? 'dragover' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
          >
            {imagePreview ? (
              <img src={imagePreview} alt="Yarn preview" className="yum-image-preview" />
            ) : (
              <div className="yum-image-placeholder">
                <ImagePlus size={32} />
                <span>{t('uploadImage')}</span>
                <span className="yum-image-hint">JPG, PNG, WebP</span>
              </div>
            )}
            {imagePreview && (
              <div className="yum-image-overlay">
                <Upload size={18} />
                <span>{t('changeImage')}</span>
              </div>
            )}
            <input
              ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
              onChange={(e) => handleImage(e.target.files[0])}
            />
          </div>

          {/* Fields */}
          <div className="yum-fields">
            <div className="yum-row">
              <Field label={t('yarnName')} required>
                <input
                  type="text" value={fields.name} placeholder={t('yarnName')}
                  onChange={(e) => set('name', e.target.value)}
                  className="yum-input"
                />
              </Field>
              <Field label={t('colour')}>
                <input
                  type="text" value={fields.colour}
                  placeholder="e.g. White, Navy Blue"
                  onChange={(e) => set('colour', e.target.value)}
                  className="yum-input"
                />
              </Field>
            </div>

            <Field label={t('woolType')}>
              <input
                type="text" value={fields.wool_type}
                placeholder="e.g. 65% Alpaca, 35% Wool"
                onChange={(e) => set('wool_type', e.target.value)}
                className="yum-input"
              />
            </Field>

            <div className="yum-row">
              <Field label={t('yardage')}>
                <input
                  type="text" value={fields.yardage}
                  placeholder="e.g. Approx. 100m per 50g"
                  onChange={(e) => set('yardage', e.target.value)}
                  className="yum-input"
                />
              </Field>
              <Field label={t('needles')}>
                <input
                  type="text" value={fields.needles}
                  placeholder="e.g. No. 3½–5"
                  onChange={(e) => set('needles', e.target.value)}
                  className="yum-input"
                />
              </Field>
            </div>

            <div className="yum-row">
              <Field label={t('tension')}>
                <input
                  type="text" value={fields.tension}
                  placeholder="e.g. 22–19 sts = 10 cm"
                  onChange={(e) => set('tension', e.target.value)}
                  className="yum-input"
                />
              </Field>
              <Field label={t('origin')}>
                <input
                  type="text" value={fields.origin}
                  placeholder="e.g. Alpaca from Peru, Wool from Australia"
                  onChange={(e) => set('origin', e.target.value)}
                  className="yum-input"
                />
              </Field>
            </div>

            <div className="yum-row">
              <Field label={t('seller')}>
                <input
                  type="text" value={fields.seller}
                  placeholder="e.g. Sandnes Garn"
                  onChange={(e) => set('seller', e.target.value)}
                  className="yum-input"
                />
              </Field>
              <Field label={t('pricePerSkein')}>
                <input
                  type="text" value={fields.price_per_skein}
                  placeholder="e.g. ca. 100kr"
                  onChange={(e) => set('price_per_skein', e.target.value)}
                  className="yum-input"
                />
              </Field>
            </div>

            <Field label={t('productInfo')}>
              <textarea
                value={fields.product_info}
                placeholder="Care instructions, properties, notes…"
                onChange={(e) => set('product_info', e.target.value)}
                className="yum-textarea"
                rows={5}
              />
            </Field>
          </div>
        </div>

        {error && <p className="yum-error">{error}</p>}

        <div className="yum-footer">
          <button className="yum-btn-cancel" onClick={onClose} disabled={saving}>
            {t('cancel')}
          </button>
          <button className="yum-btn-save" onClick={handleSubmit} disabled={saving}>
            {saving ? '…' : isEdit ? t('save') : t('addYarn')}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, required, children }) {
  return (
    <div className="yum-field">
      <label className="yum-label">
        {label}{required && <span className="yum-required">*</span>}
      </label>
      {children}
    </div>
  );
}
