/**
 * ProjectStatus.js
 * Shows start/finish button, yarn picker on start, session history.
 */

import React, { useState, useEffect } from 'react';
import { Play, CheckCircle, Clock, RotateCcw, Trash2, X, Search } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { startProject, finishProject, clearSessions, fetchYarns, yarnImageUrl, yarnColourImageUrl } from '../utils/api';
import './ProjectStatus.css';

function formatDuration(seconds, t) {
  if (seconds < 60) return `< 1${t('minutes')}`;
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts = [];
  if (d) parts.push(`${d}${t('days')}`);
  if (h) parts.push(`${h}${t('hours')}`);
  if (m) parts.push(`${m}${t('minutes')}`);
  return parts.join(' ');
}

function formatDateTime(iso, lang) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(lang === 'no' ? 'nb-NO' : 'en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function totalSeconds(sessions) {
  return sessions.reduce((sum, s) => {
    if (!s.finished_at) return sum;
    return sum + (new Date(s.finished_at) - new Date(s.started_at)) / 1000;
  }, 0);
}

// ── Yarn Pill — small display of name + colour ───────────────────────────────
function YarnPill({ name, colour, imageId, colourId }) {
  const [imgErr, setImgErr] = useState(false);
  // If we have a colour with an image, show that; otherwise show yarn image
  const imgSrc = colourId && imageId
    ? yarnColourImageUrl(imageId, colourId)
    : imageId ? yarnImageUrl(imageId) : null;
  return (
    <span className="ps-yarn-pill">
      {imgSrc && !imgErr ? (
        <img
          src={imgSrc}
          alt={name}
          className="ps-yarn-pill-img"
          onError={() => setImgErr(true)}
        />
      ) : (
        <span className="ps-yarn-pill-emoji">🧵</span>
      )}
      <span className="ps-yarn-pill-name">{name}</span>
      {colour && <span className="ps-yarn-pill-colour">{colour}</span>}
    </span>
  );
}

// ── Yarn Picker Modal ────────────────────────────────────────────────────────
function YarnPickerModal({ onSelect, onSkip, onClose, t }) {
  const [yarns, setYarns]         = useState([]);
  const [search, setSearch]       = useState('');
  const [loading, setLoading]     = useState(true);
  const [selectedYarn, setSelectedYarn] = useState(null);
  const [selectedColour, setSelectedColour] = useState(null);

  useEffect(() => {
    fetchYarns().then(y => { setYarns(y); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const filtered = yarns.filter(y =>
    !search || y.name.toLowerCase().includes(search.toLowerCase()) ||
    (y.wool_type && y.wool_type.toLowerCase().includes(search.toLowerCase()))
  );

  const handleConfirm = () => {
    onSelect(selectedYarn, selectedColour || null);
  };

  const colours = selectedYarn?.colours || [];

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="yp-modal">
        <div className="yp-header">
          <div>
            <h2 className="yp-title">{t('selectYarnTitle')}</h2>
            <p className="yp-hint">{t('selectYarnHint')}</p>
          </div>
          <button className="yp-close" onClick={onClose}><X size={20} /></button>
        </div>

        {/* Step 1: Search + yarn list */}
        <div className="yp-search-wrap">
          <Search size={15} className="yp-search-icon" />
          <input
            type="search"
            className="yp-search"
            placeholder={`${t('search')}…`}
            value={search}
            onChange={e => { setSearch(e.target.value); setSelectedYarn(null); setSelectedColour(null); }}
          />
        </div>

        <div className="yp-list">
          {loading ? (
            <div className="yp-loading"><div className="yp-spinner" /></div>
          ) : filtered.length === 0 ? (
            <p className="yp-empty">🧵 {t('noYarns')}</p>
          ) : (
            filtered.map(yarn => (
              <YarnPickerRow
                key={yarn.id}
                yarn={yarn}
                selected={selectedYarn?.id === yarn.id}
                onSelect={() => {
                  setSelectedYarn(selectedYarn?.id === yarn.id ? null : yarn);
                  setSelectedColour(null);
                }}
              />
            ))
          )}
        </div>

        {/* Step 2: colour picker — shown when a yarn is selected and has colours */}
        {selectedYarn && colours.length > 0 && (
          <div className="yp-colour-step">
            <p className="yp-colour-step-label">{t('selectColourStep')}</p>
            <div className="yp-colour-grid">
              {colours.map(c => (
                <ColourPickerDot
                  key={c.id}
                  colour={c}
                  yarnId={selectedYarn.id}
                  selected={selectedColour?.id === c.id}
                  onSelect={() => setSelectedColour(selectedColour?.id === c.id ? null : c)}
                />
              ))}
            </div>
          </div>
        )}

        <div className="yp-footer">
          <button className="yp-btn-skip" onClick={onSkip}>
            {t('continueWithoutYarn')}
          </button>
          <button
            className="yp-btn-confirm"
            onClick={handleConfirm}
            disabled={!selectedYarn}
          >
            <Play size={15} />
            {t('startProject')}
          </button>
        </div>
      </div>
    </div>
  );
}

function ColourPickerDot({ colour, yarnId, selected, onSelect }) {
  const [imgErr, setImgErr] = useState(false);
  return (
    <button
      className={`yp-colour-dot ${selected ? 'yp-colour-dot--selected' : ''}`}
      onClick={onSelect}
      title={colour.name}
    >
      <div className="yp-colour-dot-thumb">
        {colour.image_path && !imgErr
          ? <img src={yarnColourImageUrl(yarnId, colour.id)} alt={colour.name} onError={() => setImgErr(true)} />
          : <span>🎨</span>
        }
      </div>
      <span className="yp-colour-dot-name">{colour.name}</span>
      {selected && <span className="yp-colour-dot-check">✓</span>}
    </button>
  );
}

function YarnPickerRow({ yarn, selected, onSelect }) {
  const [imgErr, setImgErr] = useState(false);
  const colourCount = (yarn.colours || []).length;
  return (
    <button
      className={`yp-row ${selected ? 'yp-row--selected' : ''}`}
      onClick={onSelect}
    >
      <div className="yp-row-thumb">
        {yarn.image_path && !imgErr ? (
          <img src={yarnImageUrl(yarn.id)} alt={yarn.name} onError={() => setImgErr(true)} />
        ) : (
          <span>🧵</span>
        )}
      </div>
      <div className="yp-row-info">
        <span className="yp-row-name">{yarn.name}</span>
        <span className="yp-row-sub">
          {[yarn.wool_type, colourCount > 0 ? `${colourCount} colours` : null].filter(Boolean).join(' · ')}
        </span>
      </div>
      <div className={`yp-row-check ${selected ? 'checked' : ''}`}>
        {selected && <CheckCircle size={18} />}
      </div>
    </button>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
export default function ProjectStatus({ recipe, onUpdated }) {
  const { t, language } = useApp();
  const [loading, setLoading]         = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [showYarnPicker, setShowYarnPicker] = useState(false);

  const status   = recipe.project_status || 'none';
  const sessions = recipe.sessions || [];
  const total    = totalSeconds(sessions);

  // Find the active session's yarn data
  const activeSession = sessions.find(s => !s.finished_at);

  const handleStartClick = () => setShowYarnPicker(true);

  const handleYarnSelected = async (yarn, colour) => {
    setShowYarnPicker(false);
    setLoading(true);
    try { onUpdated(await startProject(recipe.id, yarn?.id || null, colour?.id || null)); }
    catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  const handleFinish = async () => {
    setLoading(true);
    try { onUpdated(await finishProject(recipe.id)); }
    catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  const handleClear = async () => {
    setLoading(true); setConfirmClear(false);
    try { onUpdated(await clearSessions(recipe.id)); }
    catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="project-status">

      {/* ── Status badge + main action ─────────────────────────────── */}
      <div className="ps-header">
        <span className={`ps-badge ps-badge--${status}`}>
          {status === 'active'   && <><Play size={12} /> {t('projectActive')}</>}
          {status === 'finished' && <><CheckCircle size={12} /> {t('projectFinished')}</>}
          {status === 'none'     && <><Clock size={12} /> {t('projectNone')}</>}
        </span>

        {status === 'none' || status === 'finished' ? (
          <button className="ps-btn ps-btn--start" onClick={handleStartClick} disabled={loading}>
            <Play size={15} /> {t('startProject')}
          </button>
        ) : (
          <button className="ps-btn ps-btn--finish" onClick={handleFinish} disabled={loading}>
            <CheckCircle size={15} /> {t('finishProject')}
          </button>
        )}
      </div>

      {/* ── Active session yarn + start time ──────────────────────── */}
      {status === 'active' && (
        <div className="ps-active-info">
          {activeSession?.yarn_name && (
            <div className="ps-active-yarn">
              <span className="ps-active-yarn-label">{t('yarnForProject')}</span>
              <YarnPill
                name={activeSession.yarn_name}
                colour={activeSession.yarn_colour}
                imageId={activeSession.yarn_id}
                colourId={activeSession.yarn_colour_id}
              />
            </div>
          )}
          {recipe.active_started_at && (
            <div className="ps-time-row" style={{ marginTop: 4 }}>
              <Clock size={13} />
              <span>{t('startedAt')}: {formatDateTime(recipe.active_started_at, language)}</span>
            </div>
          )}
        </div>
      )}

      {/* ── Summary stats ─────────────────────────────────────────── */}
      {sessions.length > 0 && (
        <div className="ps-stats">
          <div className="ps-stat">
            <span className="ps-stat-label"><RotateCcw size={12} /> {t('totalSessions')}</span>
            <span className="ps-stat-value">{sessions.length}</span>
          </div>
          {total > 0 && (
            <div className="ps-stat">
              <span className="ps-stat-label"><Clock size={12} /> {t('totalKnittingTime')}</span>
              <span className="ps-stat-value">{formatDuration(total, t)}</span>
            </div>
          )}
        </div>
      )}

      {/* ── Session history ────────────────────────────────────────── */}
      {sessions.length > 0 && (
        <div className="ps-history">
          {sessions.map((s, i) => {
            const dur = s.finished_at
              ? (new Date(s.finished_at) - new Date(s.started_at)) / 1000
              : null;
            return (
              <div key={s.id} className={`ps-session ${!s.finished_at ? 'ps-session--active' : ''}`}>
                <div className="ps-session-header">
                  <span className="ps-session-num">{t('session')} {i + 1}</span>
                  {!s.finished_at && <span className="ps-session-live">● {t('projectActive')}</span>}
                  {dur !== null && <span className="ps-session-dur">{formatDuration(dur, t)}</span>}
                </div>

                {/* Yarn used in this session */}
                {s.yarn_name && (
                  <div className="ps-session-yarn">
                    <YarnPill
                      name={s.yarn_name}
                      colour={s.yarn_colour}
                      imageId={s.yarn_id}
                      colourId={s.yarn_colour_id}
                    />
                  </div>
                )}

                <div className="ps-session-times">
                  <div className="ps-time-row">
                    <Play size={10} /><span>{formatDateTime(s.started_at, language)}</span>
                  </div>
                  {s.finished_at && (
                    <div className="ps-time-row">
                      <CheckCircle size={10} /><span>{formatDateTime(s.finished_at, language)}</span>
                    </div>
                  )}
                </div>
                {dur !== null && total > 0 && (
                  <div className="ps-session-bar">
                    <div className="ps-session-bar-fill" style={{ width: `${Math.round((dur / total) * 100)}%` }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Clear sessions ─────────────────────────────────────────── */}
      {sessions.length > 0 && (
        <div className="ps-clear-wrap">
          {confirmClear ? (
            <div className="ps-confirm-row">
              <span className="ps-confirm-text">{t('clearSessionsConfirm')}</span>
              <button className="ps-confirm-btn ps-confirm-btn--yes" onClick={handleClear} disabled={loading}>{t('clearSessionsYes')}</button>
              <button className="ps-confirm-btn ps-confirm-btn--no" onClick={() => setConfirmClear(false)}>{t('clearSessionsNo')}</button>
            </div>
          ) : (
            <button className="ps-clear-btn" onClick={() => setConfirmClear(true)} disabled={loading}>
              <Trash2 size={13} /> {t('clearSessions')}
            </button>
          )}
        </div>
      )}

      {/* ── Yarn picker modal ──────────────────────────────────────── */}
      {showYarnPicker && (
        <YarnPickerModal
          t={t}
          onSelect={handleYarnSelected}
          onSkip={() => handleYarnSelected(null, null)}
          onClose={() => setShowYarnPicker(false)}
        />
      )}
    </div>
  );
}
