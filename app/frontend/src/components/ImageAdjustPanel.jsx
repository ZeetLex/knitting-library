import React, { useState } from 'react';
import { X } from 'lucide-react';

const DEFAULT_ADJUSTMENTS = {
  brightness: 0,
  contrast: 0,
  gamma: 1,
  saturation: 0,
  warmth: 0,
  sharpness: 0,
};

export default function ImageAdjustPanel({ t, imageSrc, onClose, onApply, onRestore }) {
  const [values, setValues] = useState(DEFAULT_ADJUSTMENTS);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const f = (key, value) => setValues(prev => ({ ...prev, [key]: Number(value) }));
  const previewFilter = [
    `brightness(${1 + values.brightness / 100})`,
    `contrast(${1 + values.contrast / 100})`,
    `saturate(${Math.max(0, 1 + values.saturation / 100)})`,
  ].join(' ');

  const handleApply = async () => {
    setSaving(true); setError('');
    try { await onApply(values); }
    catch (e) { setError(e.message || t('adjustImageError')); setSaving(false); }
  };

  const handleRestore = async () => {
    if (!window.confirm(t('restoreOriginalConfirm'))) return;
    setSaving(true); setError('');
    try { await onRestore(); }
    catch (e) { setError(e.message || t('restoreOriginalError')); setSaving(false); }
  };

  const sliders = [
    ['brightness', t('adjustBrightness'), -100, 100, 1],
    ['contrast', t('adjustContrast'), -100, 100, 1],
    ['gamma', t('adjustGamma'), 0.2, 3, 0.05],
    ['saturation', t('adjustSaturation'), -100, 100, 1],
    ['warmth', t('adjustWarmth'), -100, 100, 1],
    ['sharpness', t('adjustSharpness'), -100, 100, 1],
  ];

  return (
    <div className="adjust-panel-overlay" onClick={onClose}>
      <div className="adjust-panel" onClick={e => e.stopPropagation()}>
        <div className="adjust-panel-header">
          <div>
            <h3>{t('adjustImage')}</h3>
            <p>{t('adjustImageHint')}</p>
          </div>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>
        <div className="adjust-panel-body">
          <div className="adjust-preview">
            <img src={imageSrc} alt="" style={{ filter: previewFilter }} />
          </div>
          <div className="adjust-sliders">
            {sliders.map(([key, label, min, max, step]) => (
              <label className="adjust-slider" key={key}>
                <span>{label}<strong>{values[key]}</strong></span>
                <input
                  type="range"
                  min={min}
                  max={max}
                  step={step}
                  value={values[key]}
                  onChange={e => f(key, e.target.value)}
                />
              </label>
            ))}
          </div>
        </div>
        {error && <p className="status-error adjust-error">{error}</p>}
        <div className="adjust-panel-actions">
          <button className="btn-secondary" onClick={() => setValues(DEFAULT_ADJUSTMENTS)} disabled={saving}>{t('resetSliders')}</button>
          <button className="btn-secondary" onClick={handleRestore} disabled={saving}>{t('restoreOriginal')}</button>
          <button className="btn-secondary" onClick={onClose} disabled={saving}>{t('cancel')}</button>
          <button className="btn-primary" onClick={handleApply} disabled={saving}>{saving ? t('saving') : t('apply')}</button>
        </div>
      </div>
    </div>
  );
}
