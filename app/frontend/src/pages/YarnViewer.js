/**
 * YarnViewer.js
 * Full detail view for a single yarn, with colour variant management.
 */

import React, { useState, useEffect, useRef } from 'react';
import { ArrowLeft, Pencil, Trash2, Plus, X } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import {
  fetchYarn, deleteYarn, yarnImageUrl,
  addYarnColour, deleteYarnColour, yarnColourImageUrl
} from '../utils/api';
import YarnUploadModal from '../components/YarnUploadModal';
import './YarnViewer.css';

export default function YarnViewer({ yarnId, onBack, onDeleted }) {
  const { t } = useApp();
  const [yarn, setYarn]             = useState(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [editing, setEditing]       = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [imgError, setImgError]     = useState(false);
  const [activeColour, setActiveColour] = useState(null);
  const [addingColour, setAddingColour]     = useState(false);
  const [newColourName, setNewColourName]   = useState('');
  const [newColourPrice, setNewColourPrice] = useState('');
  const [newColourFile, setNewColourFile]   = useState(null);
  const [newColourPreview, setNewColourPreview] = useState(null);
  const [colourSaving, setColourSaving]     = useState(false);
  const [colourError, setColourError]       = useState('');
  const fileInputRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    fetchYarn(yarnId)
      .then(y => { setYarn(y); setLoading(false); })
      .catch(() => { setError('Could not load this yarn.'); setLoading(false); });
  }, [yarnId]);

  const handleDelete = async () => {
    try { await deleteYarn(yarnId); onDeleted(); }
    catch (e) { alert(e.message); }
  };

  const handleFileChange = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setNewColourFile(f);
    setNewColourPreview(URL.createObjectURL(f));
  };

  // Clipboard paste — active while the add-colour form is open
  useEffect(() => {
    if (!addingColour) return;
    const handlePaste = (e) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile();
          if (file) {
            setNewColourFile(file);
            setNewColourPreview(URL.createObjectURL(file));
            break;
          }
        }
      }
    };
    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
  }, [addingColour]);

  const handleAddColour = async () => {
    if (!newColourName.trim()) { setColourError(t('colourName') + ' is required'); return; }
    setColourSaving(true); setColourError('');
    try {
      const fd = new FormData();
      fd.append('name', newColourName.trim());
      if (newColourPrice.trim()) fd.append('price', newColourPrice.trim());
      if (newColourFile) fd.append('image', newColourFile);
      await addYarnColour(yarnId, fd);
      const updated = await fetchYarn(yarnId);
      setYarn(updated);
      setNewColourName(''); setNewColourPrice(''); setNewColourFile(null); setNewColourPreview(null);
      setAddingColour(false);
    } catch (e) {
      setColourError(e.message);
    } finally {
      setColourSaving(false);
    }
  };

  const handleDeleteColour = async (colourId) => {
    try {
      await deleteYarnColour(yarnId, colourId);
      const updated = await fetchYarn(yarnId);
      setYarn(updated);
      if (activeColour?.id === colourId) setActiveColour(null);
    } catch (e) { alert(e.message); }
  };

  if (loading) return <div className="yv-loading"><div className="spinner" style={{ width: 32, height: 32 }} /></div>;
  if (error || !yarn) return (
    <div className="yv-error"><p>{error || 'Yarn not found'}</p><button onClick={onBack}>{t('backToYarns')}</button></div>
  );

  const colours = yarn.colours || [];

  return (
    <div className="yv-page">
      <div className="yv-topbar">
        <button className="yv-back-btn" onClick={onBack}>
          <ArrowLeft size={18} /> {t('backToYarns')}
        </button>
        <div className="yv-actions">
          <button className="yv-action-btn" onClick={() => setEditing(true)} title={t('editYarn')}>
            <Pencil size={17} />
          </button>
          {confirmDel ? (
            <div className="yv-confirm-row">
              <span>{t('deleteYarnConfirm')}</span>
              <button className="yv-confirm-yes" onClick={handleDelete}>{t('clearSessionsYes')}</button>
              <button className="yv-confirm-no" onClick={() => setConfirmDel(false)}>{t('clearSessionsNo')}</button>
            </div>
          ) : (
            <button className="yv-action-btn danger" onClick={() => setConfirmDel(true)} title={t('deleteYarn')}>
              <Trash2 size={17} />
            </button>
          )}
        </div>
      </div>

      <div className="yv-body">
        {/* Left: main image or active colour preview */}
        <div className="yv-image-col">
          {activeColour ? (
            <ColourPreview yarn={yarn} colour={activeColour} onClose={() => setActiveColour(null)} />
          ) : yarn.image_path && !imgError ? (
            <div className="yv-image-wrap">
              <img src={yarnImageUrl(yarn.id)} alt={yarn.name} className="yv-image" onError={() => setImgError(true)} />
            </div>
          ) : (
            <div className="yv-image-placeholder">🧵</div>
          )}
        </div>

        {/* Right: specs + colours */}
        <div className="yv-details">
          <h1 className="yv-name">{yarn.name}</h1>
          <div className="yv-specs">
            {yarn.wool_type    && <SpecRow icon="🐑" label={t('woolType')}     value={yarn.wool_type} />}
            {yarn.yardage      && <SpecRow icon="📏" label={t('yardage')}      value={yarn.yardage} />}
            {yarn.needles      && <SpecRow icon="🪡" label={t('needles')}      value={yarn.needles} />}
            {yarn.tension      && <SpecRow icon="📐" label={t('tension')}      value={yarn.tension} />}
            {yarn.origin       && <SpecRow icon="🌍" label={t('origin')}       value={yarn.origin} />}
            {yarn.seller       && <SpecRow icon="🏪" label={t('seller')}       value={yarn.seller} />}
            {yarn.price_per_skein && <SpecRow icon="💰" label={t('pricePerSkein')} value={yarn.price_per_skein} />}
          </div>

          {yarn.product_info && (
            <div className="yv-product-info">
              <h3 className="yv-section-title">{t('productInfo')}</h3>
              <div className="yv-product-text">
                {yarn.product_info.split('\n').map((line, i) =>
                  line.trim() ? <p key={i}>{line}</p> : <br key={i} />
                )}
              </div>
            </div>
          )}

          {/* ── Colours section ───────────────────────────────────── */}
          <div className="yv-colours-section">
            <div className="yv-colours-header">
              <h3 className="yv-section-title">{t('colours')}</h3>
              <button className="yv-add-colour-btn" onClick={() => { setAddingColour(true); setColourError(''); }}>
                <Plus size={14} /> {t('addColour')}
              </button>
            </div>

            {addingColour && (
              <div className="yv-add-colour-form">
                <input
                  type="text"
                  className="yv-colour-name-input"
                  placeholder={t('colourNamePlaceholder')}
                  value={newColourName}
                  onChange={e => setNewColourName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleAddColour()}
                  autoFocus
                />
                <input
                  type="text"
                  className="yv-colour-name-input"
                  placeholder={t('colourPricePlaceholder')}
                  value={newColourPrice}
                  onChange={e => setNewColourPrice(e.target.value)}
                />
                <div className="yv-colour-photo-drop" onClick={() => fileInputRef.current?.click()}>
                  {newColourPreview
                    ? <img src={newColourPreview} alt="preview" className="yv-colour-photo-preview" />
                    : <span className="yv-colour-photo-hint">📷 {t('colourPhoto')} · paste</span>
                  }
                </div>
                <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleFileChange} />
                {colourError && <p className="yv-colour-error">{colourError}</p>}
                <div className="yv-add-colour-btns">
                  <button className="yv-colour-save-btn" onClick={handleAddColour} disabled={colourSaving}>
                    {colourSaving ? t('addingColour') : t('addColour')}
                  </button>
                  <button className="yv-colour-cancel-btn" onClick={() => {
                    setAddingColour(false); setNewColourName(''); setNewColourPrice('');
                    setNewColourFile(null); setNewColourPreview(null); setColourError('');
                  }}>{t('cancel')}</button>
                </div>
              </div>
            )}

            {colours.length === 0 && !addingColour
              ? <p className="yv-no-colours">{t('noColours')}</p>
              : (
                <div className="yv-colours-grid">
                  {colours.map(c => (
                    <ColourSwatch
                      key={c.id} colour={c} yarnId={yarn.id}
                      active={activeColour?.id === c.id}
                      onClick={() => setActiveColour(activeColour?.id === c.id ? null : c)}
                      onDelete={() => handleDeleteColour(c.id)}
                      t={t}
                    />
                  ))}
                </div>
              )
            }
          </div>

          <p className="yv-date">
            {t('yarnAdded')} {new Date(yarn.created_date).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })}
          </p>
        </div>
      </div>

      {editing && (
        <YarnUploadModal
          editYarn={yarn}
          onClose={() => setEditing(false)}
          onSuccess={(updated) => { setYarn(updated); setEditing(false); setImgError(false); }}
        />
      )}
    </div>
  );
}

function ColourSwatch({ colour, yarnId, active, onClick, onDelete, t }) {
  const [imgErr, setImgErr] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  return (
    <div className={`yv-colour-swatch ${active ? 'yv-colour-swatch--active' : ''}`}>
      <button className="yv-swatch-thumb" onClick={onClick}>
        {colour.image_path && !imgErr
          ? <img src={yarnColourImageUrl(yarnId, colour.id)} alt={colour.name} onError={() => setImgErr(true)} />
          : <span className="yv-swatch-emoji">🎨</span>
        }
      </button>
      <div className="yv-swatch-info">
        <div className="yv-swatch-text">
          <span className="yv-swatch-name">{colour.name}</span>
          {colour.price && <span className="yv-swatch-price">{colour.price}</span>}
        </div>
        {confirmDel ? (
          <div className="yv-swatch-confirm">
            <button className="yv-swatch-del-yes" onClick={onDelete}>✓</button>
            <button className="yv-swatch-del-no" onClick={() => setConfirmDel(false)}>✕</button>
          </div>
        ) : (
          <button className="yv-swatch-del-btn" onClick={() => setConfirmDel(true)} title={t('deleteColour')}>
            <Trash2 size={12} />
          </button>
        )}
      </div>
    </div>
  );
}

function ColourPreview({ yarn, colour, onClose }) {
  const [imgErr, setImgErr] = useState(false);
  return (
    <div className="yv-colour-preview">
      <button className="yv-colour-preview-close" onClick={onClose}><X size={18} /></button>
      {colour.image_path && !imgErr
        ? <img src={yarnColourImageUrl(yarn.id, colour.id)} alt={colour.name} className="yv-colour-preview-img" onError={() => setImgErr(true)} />
        : <div className="yv-colour-preview-placeholder">🎨</div>
      }
      <p className="yv-colour-preview-name">
        {colour.name}{colour.price ? ` · ${colour.price}` : ''}
      </p>
    </div>
  );
}

function SpecRow({ icon, label, value }) {
  return (
    <div className="yv-spec-row">
      <span className="yv-spec-icon">{icon}</span>
      <span className="yv-spec-label">{label}</span>
      <span className="yv-spec-value">{value}</span>
    </div>
  );
}
