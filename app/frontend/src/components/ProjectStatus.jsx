/**
 * ProjectStatus.js
 * Shows start/finish button, yarn picker on start, session history.
 */

import React, { useState, useEffect } from 'react';
import { Play, CheckCircle, Clock, RotateCcw, Trash2, X, Search, Minus, Plus, Settings, Save } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import {
  startProject,
  finishProject,
  clearSessions,
  fetchYarns,
  yarnImageUrl,
  yarnColourImageUrl,
  fetchInventory,
  saveFeedback,
  updateProjectSession,
  reopenProjectSession,
  deleteProjectSession,
} from '../utils/api';
import FeedbackModal from './FeedbackModal';
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
  // Compact format: "9 Mar, 06:29" — saves significant horizontal space
  return new Date(iso).toLocaleString(lang === 'no' ? 'nb-NO' : 'en-GB', {
    day: 'numeric', month: 'short',
    hour: '2-digit', minute: '2-digit',
  });
}

function totalSeconds(sessions) {
  return sessions.reduce((sum, s) => {
    if (!s.finished_at) return sum;
    return sum + (new Date(s.finished_at) - new Date(s.started_at)) / 1000;
  }, 0);
}

function isoToLocalInput(iso) {
  if (!iso) return '';
  if (!/[zZ]|[+-]\d\d:\d\d$/.test(iso)) return iso.slice(0, 16);
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function localInputToIso(value) {
  if (!value) return '';
  return value.length === 16 ? `${value}:00` : value;
}

// ── Yarn Pill — small display of name + colour ───────────────────────────────
function YarnPill({ name, colour, imageId, colourId }) {
  const [imgErr, setImgErr] = useState(false);
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
      <span className="ps-yarn-pill-text">
        <span className="ps-yarn-pill-name">{name}</span>
        {colour && <span className="ps-yarn-pill-colour">{colour}</span>}
      </span>
    </span>
  );
}

// ── Yarn Picker Modal ────────────────────────────────────────────────────────
function YarnPickerModal({ onSelect, onSkip, onClose, t, confirmLabel, skipLabel }) {
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
            {skipLabel || t('continueWithoutYarn')}
          </button>
          <button
            className="yp-btn-confirm"
            onClick={handleConfirm}
            disabled={!selectedYarn}
          >
            <Play size={15} />
            {confirmLabel || t('startProject')}
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

function ProjectSessionEditor({ recipeId, session, t, onClose, onUpdated }) {
  const [startedAt, setStartedAt] = useState(() => isoToLocalInput(session.started_at));
  const [selectedYarn, setSelectedYarn] = useState(() => (
    session.yarn_id ? { id: session.yarn_id, name: session.yarn_name || t('unknownYarn') } : null
  ));
  const [selectedColour, setSelectedColour] = useState(() => (
    session.yarn_colour_id ? { id: session.yarn_colour_id, name: session.yarn_colour || '' } : null
  ));
  const [showYarnPicker, setShowYarnPicker] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const updated = await updateProjectSession(recipeId, session.id, {
        started_at: localInputToIso(startedAt),
        yarn_id: selectedYarn?.id || null,
        yarn_colour_id: selectedColour?.id || null,
      });
      onUpdated(updated);
      onClose();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  };

  const reopen = async () => {
    setBusy(true);
    try {
      const updated = await reopenProjectSession(recipeId, session.id);
      onUpdated(updated);
      onClose();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  };

  const deleteSession = async () => {
    setBusy(true);
    try {
      const updated = await deleteProjectSession(recipeId, session.id);
      onUpdated(updated);
      onClose();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  };

  return (
    <>
      <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
        <div className="ps-edit-modal">
          <div className="ps-edit-header">
            <div>
              <h3>{t('editProjectSession')}</h3>
              <p>{t('editProjectSessionHint')}</p>
            </div>
            <button className="ps-edit-close" onClick={onClose} disabled={busy} aria-label={t('close')}>
              <X size={18} />
            </button>
          </div>

          <div className="ps-edit-body">
            <label className="ps-edit-field">
              <span>{t('startedAt')}</span>
              <input
                type="datetime-local"
                value={startedAt}
                onChange={e => setStartedAt(e.target.value)}
              />
            </label>

            <div className="ps-edit-field">
              <span>{t('yarnForProject')}</span>
              <div className="ps-edit-yarn-row">
                {selectedYarn ? (
                  <YarnPill
                    name={selectedYarn.name}
                    colour={selectedColour?.name}
                    imageId={selectedYarn.id}
                    colourId={selectedColour?.id}
                  />
                ) : (
                  <span className="ps-edit-empty-yarn">{t('noYarnSelected')}</span>
                )}
              </div>
              <div className="ps-edit-inline-actions">
                <button type="button" onClick={() => setShowYarnPicker(true)} disabled={busy}>
                  {t('changeYarn')}
                </button>
                <button
                  type="button"
                  onClick={() => { setSelectedYarn(null); setSelectedColour(null); }}
                  disabled={busy || !selectedYarn}
                >
                  {t('clearYarn')}
                </button>
              </div>
            </div>
          </div>

          <div className="ps-edit-actions">
            {session.finished_at && (
              <button className="ps-edit-secondary" onClick={reopen} disabled={busy}>
                <Play size={14} /> {t('reopenProjectSession')}
              </button>
            )}
            {confirmDelete ? (
              <div className="ps-edit-delete-confirm">
                <span>{t('deleteProjectSessionConfirm')}</span>
                <button className="ps-edit-danger" onClick={deleteSession} disabled={busy}>{t('clearSessionsYes')}</button>
                <button className="ps-edit-secondary" onClick={() => setConfirmDelete(false)} disabled={busy}>{t('clearSessionsNo')}</button>
              </div>
            ) : (
              <button className="ps-edit-danger" onClick={() => setConfirmDelete(true)} disabled={busy}>
                <Trash2 size={14} /> {t('deleteProjectSession')}
              </button>
            )}
            <button className="ps-edit-save" onClick={save} disabled={busy || !startedAt}>
              <Save size={14} /> {t('saveChanges')}
            </button>
          </div>
        </div>
      </div>

      {showYarnPicker && (
        <YarnPickerModal
          t={t}
          confirmLabel={t('useSelectedYarn')}
          skipLabel={t('clearYarn')}
          onSelect={(yarn, colour) => {
            setSelectedYarn(yarn);
            setSelectedColour(colour || null);
            setShowYarnPicker(false);
          }}
          onSkip={() => {
            setSelectedYarn(null);
            setSelectedColour(null);
            setShowYarnPicker(false);
          }}
          onClose={() => setShowYarnPicker(false)}
        />
      )}
    </>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
export default function ProjectStatus({ recipe, onUpdated, enableExternalControls = false, controlsOnly = false }) {
  const { t, language, user } = useApp();
  const [loading, setLoading]         = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [showYarnPicker, setShowYarnPicker] = useState(false);
  // Inventory step — shown after yarn is picked
  const [showInventoryPicker, setShowInventoryPicker] = useState(false);
  const [pendingYarn, setPendingYarn]   = useState(null);   // { yarn, colour }
  const [inventoryItems, setInventoryItems] = useState([]);
  const [selectedInvItem, setSelectedInvItem] = useState(null);
  const [skeinsToUse, setSkeinsToUse]   = useState(1);
  // Feedback modal
  const [feedbackMode, setFeedbackMode] = useState(null);      // 'submit' | 'view' | null
  const [feedbackSession, setFeedbackSession] = useState(null); // session object for view mode
  const [pendingFinishSessionId, setPendingFinishSessionId] = useState(null);
  const [editingSession, setEditingSession] = useState(null);

  const status   = recipe.project_status || 'none';
  const sessions = recipe.sessions || [];
  const total    = totalSeconds(sessions);
  const isAdmin = !!user?.is_admin;

  // Find the active session selected by the backend; admins can see several.
  const activeSession = sessions.find(s => s.id === recipe.active_session_id)
    || [...sessions].reverse().find(s => !s.finished_at);

  const handleStartClick = () => setShowYarnPicker(true);

  useEffect(() => {
    if (!enableExternalControls) return undefined;
    const handleProjectAction = () => {
      if ((recipe.project_status || 'none') === 'active') return;
      setShowYarnPicker(true);
    };
    window.addEventListener('knitting-recipe-start-project', handleProjectAction);
    return () => window.removeEventListener('knitting-recipe-start-project', handleProjectAction);
  }, [enableExternalControls, recipe.project_status]);

  // Called when yarn (and optional colour) is chosen in the yarn picker
  const handleYarnSelected = async (yarn, colour) => {
    setShowYarnPicker(false);
    // Load matching inventory items for this yarn+colour
    try {
      const allItems = await fetchInventory({ type: 'yarn' });
      const matching = allItems.filter(i =>
        (!yarn || i.yarn_id === yarn?.id) &&
        (!colour || i.yarn_colour_id === colour?.id)
      );
      if (matching.length > 0) {
        setPendingYarn({ yarn, colour });
        setInventoryItems(matching);
        setSelectedInvItem(null);
        setSkeinsToUse(1);
        setShowInventoryPicker(true);
        return;
      }
    } catch {}
    // No matching inventory — start directly
    await doStartProject(yarn, colour, null, 0);
  };

  const doStartProject = async (yarn, colour, invItemId, skeins) => {
    setLoading(true);
    try {
      const result = await startProject(
        recipe.id,
        yarn?.id || null,
        colour?.id || null,
        invItemId || null,
        skeins || 0
      );
      onUpdated(result);
    } catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  const handleInventoryConfirm = async () => {
    setShowInventoryPicker(false);
    await doStartProject(
      pendingYarn?.yarn,
      pendingYarn?.colour,
      selectedInvItem?.id || null,
      selectedInvItem ? skeinsToUse : 0
    );
    setPendingYarn(null);
  };

  const handleInventorySkip = async () => {
    setShowInventoryPicker(false);
    await doStartProject(pendingYarn?.yarn, pendingYarn?.colour, null, 0);
    setPendingYarn(null);
  };

  // Finish button clicked → find the active session ID, show feedback modal first
  const handleFinish = () => {
    setPendingFinishSessionId(activeSession?.id || null);
    setFeedbackMode('submit');
  };

  // User submitted feedback → save it, then finish the project
  const handleFeedbackSubmit = async ({ recipe: rr, difficulty, result, notes }) => {
    setLoading(true);
    try {
      // Save feedback AND finish the session in one atomic backend call
      const updated = await saveFeedback(recipe.id, {
        session_id: pendingFinishSessionId,
        rating_recipe: rr,
        rating_difficulty: difficulty,
        rating_result: result,
        notes,
        finish_session: true,   // backend finishes the session atomically
      });
      onUpdated(updated);
    } catch (e) { alert(e.message); }
    finally {
      setLoading(false);
      setFeedbackMode(null);
      setPendingFinishSessionId(null);
    }
  };

  // User skipped feedback → just finish
  const handleFeedbackSkip = async () => {
    setFeedbackMode(null);
    setLoading(true);
    try { onUpdated(await finishProject(recipe.id, pendingFinishSessionId)); }
    catch (e) { alert(e.message); }
    finally { setLoading(false); setPendingFinishSessionId(null); }
  };

  // Clicking a finished session → show its feedback in view mode
  const handleSessionClick = (session) => {
    if (!session.finished_at) return; // only finished sessions
    setFeedbackSession(session);
    setFeedbackMode('view');
  };

  const handleClear = async () => {
    setLoading(true); setConfirmClear(false);
    try { onUpdated(await clearSessions(recipe.id)); }
    catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  const modals = (
    <>
      {showYarnPicker && (
        <YarnPickerModal
          t={t}
          onSelect={handleYarnSelected}
          onSkip={() => handleYarnSelected(null, null)}
          onClose={() => setShowYarnPicker(false)}
        />
      )}

      {showInventoryPicker && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && handleInventorySkip()}>
          <div className="inv-use-modal">
            <div className="inv-use-header">
              <h3>{t('useFromInventory')}</h3>
              <button className="inv-modal-close" onClick={handleInventorySkip}><X size={18} /></button>
            </div>
            <p className="inv-use-sub">
              {pendingYarn?.yarn
                ? `${pendingYarn.yarn.name}${pendingYarn.colour ? ` — ${pendingYarn.colour.name}` : ''}`
                : ''}
            </p>

            <div className="inv-use-items">
              <button
                className={`inv-use-item ${!selectedInvItem ? 'inv-use-item--selected' : ''}`}
                onClick={() => setSelectedInvItem(null)}
              >
                <span className="inv-use-item-name">{t('noInventoryItem')}</span>
              </button>

              {inventoryItems.map(item => (
                <button
                  key={item.id}
                  className={`inv-use-item ${selectedInvItem?.id === item.id ? 'inv-use-item--selected' : ''}`}
                  onClick={() => setSelectedInvItem(item)}
                >
                  <div className="inv-use-item-info">
                    <span className="inv-use-item-name">{item.name}</span>
                    <span className="inv-use-item-stock">{t('currentStock')}: <strong>{item.quantity}</strong> {t('skeinCount')}</span>
                    {item.purchase_price && <span className="inv-use-item-price">💰 {item.purchase_price}</span>}
                  </div>
                  {selectedInvItem?.id === item.id && <span className="inv-use-check">✓</span>}
                </button>
              ))}
            </div>

            {selectedInvItem && (
              <div className="inv-use-skeins">
                <span className="inv-use-skeins-label">{t('skeinsToUse')}</span>
                <div className="inv-qty-row">
                  <button className="inv-qty-btn" onClick={() => setSkeinsToUse(s => Math.max(1, s - 1))}><Minus size={14} /></button>
                  <span className="inv-qty-value">{skeinsToUse}<span className="inv-qty-unit">{t('skeinCount')}</span></span>
                  <button className="inv-qty-btn" onClick={() => setSkeinsToUse(s => Math.min(selectedInvItem.quantity, s + 1))}><Plus size={14} /></button>
                </div>
                {skeinsToUse > 0 && (
                  <p className="inv-use-remaining">
                    → {Math.max(0, selectedInvItem.quantity - skeinsToUse)} {t('skeinCount')} {t('currentStock').toLowerCase()}
                  </p>
                )}
              </div>
            )}

            <div className="inv-use-footer">
              <button className="inv-modal-cancel" onClick={handleInventorySkip}>{t('noInventoryItem')}</button>
              <button className="inv-modal-save" onClick={handleInventoryConfirm}>
                {t('startProject')}
              </button>
            </div>
          </div>
        </div>
      )}

      {feedbackMode && (
        <FeedbackModal
          mode={feedbackMode}
          feedbackList={feedbackMode === 'view' ? (feedbackSession?.feedback || []) : []}
          onSubmit={handleFeedbackSubmit}
          onSkip={handleFeedbackSkip}
          onClose={() => { setFeedbackMode(null); setFeedbackSession(null); }}
          loading={loading}
        />
      )}

      {editingSession && (
        <ProjectSessionEditor
          recipeId={recipe.id}
          session={editingSession}
          t={t}
          onClose={() => setEditingSession(null)}
          onUpdated={onUpdated}
        />
      )}
    </>
  );

  if (controlsOnly) return modals;

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
          <div className="ps-time-row" style={{ marginTop: 4 }}>
            <span>{t('startedBy')}: {activeSession?.username || recipe.active_username || t('unknownUser')}</span>
          </div>
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
              <div
                key={s.id}
                className={`ps-session ${!s.finished_at ? 'ps-session--active' : 'ps-session--finished'}`}
                onClick={() => handleSessionClick(s)}
                style={s.finished_at ? { cursor: 'pointer' } : {}}
              >
                <div className="ps-session-header">
                  <span className="ps-session-num">{t('session')} {i + 1}</span>
                  {!s.finished_at && <span className="ps-session-live">● {t('projectActive')}</span>}
                  {s.finished_at && s.feedback?.length > 0 && (
                    <span className="ps-session-has-feedback" title={t('feedbackViewTitle')}>
                      ★ {((s.feedback.reduce((a, f) => a + f.rating_recipe + f.rating_difficulty + f.rating_result, 0)) / (s.feedback.length * 3)).toFixed(1)}
                    </span>
                  )}
                  <button
                    className="ps-session-settings"
                    onClick={e => { e.stopPropagation(); setEditingSession(s); }}
                    title={t('editProjectSession')}
                    aria-label={t('editProjectSession')}
                  >
                    <Settings size={13} />
                  </button>
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
                    <span>{t('startedBy')}: {s.username || t('unknownUser')}</span>
                  </div>
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
              <span className="ps-confirm-text">{isAdmin ? t('clearAllSessionsConfirm') : t('clearMySessionsConfirm')}</span>
              <button className="ps-confirm-btn ps-confirm-btn--yes" onClick={handleClear} disabled={loading}>{t('clearSessionsYes')}</button>
              <button className="ps-confirm-btn ps-confirm-btn--no" onClick={() => setConfirmClear(false)}>{t('clearSessionsNo')}</button>
            </div>
          ) : (
            <button className="ps-clear-btn" onClick={() => setConfirmClear(true)} disabled={loading}>
              <Trash2 size={13} /> {isAdmin ? t('clearAllSessions') : t('clearMySessions')}
            </button>
          )}
        </div>
      )}

      {modals}
    </div>
  );
}
