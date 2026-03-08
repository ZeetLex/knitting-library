/**
 * YarnViewer.js
 * Full detail view for a single yarn.
 */

import React, { useState, useEffect } from 'react';
import { ArrowLeft, Pencil, Trash2 } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchYarn, deleteYarn, yarnImageUrl } from '../utils/api';
import YarnUploadModal from '../components/YarnUploadModal';
import './YarnViewer.css';

export default function YarnViewer({ yarnId, onBack, onDeleted }) {
  const { t } = useApp();
  const [yarn, setYarn]           = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [editing, setEditing]     = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [imgError, setImgError]   = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchYarn(yarnId)
      .then(setYarn)
      .catch(() => setError('Could not load this yarn.'))
      .finally(() => setLoading(false));
  }, [yarnId]);

  const handleDelete = async () => {
    try { await deleteYarn(yarnId); onDeleted(); }
    catch (e) { alert(e.message); }
  };

  if (loading) return (
    <div className="yv-loading">
      <div className="spinner" style={{ width: 32, height: 32 }} />
    </div>
  );
  if (error || !yarn) return (
    <div className="yv-error">
      <p>{error || 'Yarn not found'}</p>
      <button onClick={onBack}>{t('backToYarns')}</button>
    </div>
  );

  return (
    <div className="yv-page">
      {/* ── Top bar ──────────────────────────────────────────────────── */}
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

      {/* ── Main layout ──────────────────────────────────────────────── */}
      <div className="yv-body">
        {/* Image */}
        {yarn.image_path && !imgError ? (
          <div className="yv-image-wrap">
            <img
              src={yarnImageUrl(yarn.id)}
              alt={yarn.name}
              className="yv-image"
              onError={() => setImgError(true)}
            />
          </div>
        ) : (
          <div className="yv-image-placeholder">🧵</div>
        )}

        {/* Details */}
        <div className="yv-details">
          <h1 className="yv-name">{yarn.name}</h1>
          {yarn.wool_type && <p className="yv-wool-type">{yarn.wool_type}</p>}

          <div className="yv-specs">
            {yarn.yardage && (
              <SpecRow icon="📏" label={t('yardage')} value={yarn.yardage} />
            )}
            {yarn.needles && (
              <SpecRow icon="🪡" label={t('needles')} value={yarn.needles} />
            )}
            {yarn.tension && (
              <SpecRow icon="📐" label={t('tension')} value={yarn.tension} />
            )}
            {yarn.origin && (
              <SpecRow icon="🌍" label={t('origin')} value={yarn.origin} />
            )}
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

          <p className="yv-date">
            {t('yarnAdded')} {new Date(yarn.created_date).toLocaleDateString(
              undefined, { year: 'numeric', month: 'long', day: 'numeric' }
            )}
          </p>
        </div>
      </div>

      {/* Edit modal */}
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

function SpecRow({ icon, label, value }) {
  return (
    <div className="yv-spec-row">
      <span className="yv-spec-icon">{icon}</span>
      <span className="yv-spec-label">{label}</span>
      <span className="yv-spec-value">{value}</span>
    </div>
  );
}
