/**
 * ProjectStatus.js
 * Shows start/finish button, session history, and total knitting time.
 * Used inside the RecipeViewer sidebar.
 */

import React, { useState } from 'react';
import { Play, CheckCircle, Clock, RotateCcw, Trash2 } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { startProject, finishProject, clearSessions } from '../utils/api';
import './ProjectStatus.css';

// ── Format a duration in seconds into "2d 3h 45m" ──────────────────────────
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

// ── Format ISO string to local date + time ──────────────────────────────────
function formatDateTime(iso, lang) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(lang === 'no' ? 'nb-NO' : 'en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

// ── Calculate total seconds across all finished sessions ────────────────────
function totalSeconds(sessions) {
  return sessions.reduce((sum, s) => {
    if (!s.finished_at) return sum;
    return sum + (new Date(s.finished_at) - new Date(s.started_at)) / 1000;
  }, 0);
}

export default function ProjectStatus({ recipe, onUpdated }) {
  const { t, language } = useApp();
  const [loading, setLoading]           = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  const status   = recipe.project_status || 'none';
  const sessions = recipe.sessions || [];
  const finished = sessions.filter(s => s.finished_at);
  const total    = totalSeconds(sessions);

  const handleStart = async () => {
    setLoading(true);
    try { onUpdated(await startProject(recipe.id)); }
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
    setLoading(true);
    setConfirmClear(false);
    try { onUpdated(await clearSessions(recipe.id)); }
    catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="project-status">

      {/* ── Status badge + main action button ─────────────────────────── */}
      <div className="ps-header">
        <span className={`ps-badge ps-badge--${status}`}>
          {status === 'active'   && <><Play size={12} /> {t('projectActive')}</>}
          {status === 'finished' && <><CheckCircle size={12} /> {t('projectFinished')}</>}
          {status === 'none'     && <><Clock size={12} /> {t('projectNone')}</>}
        </span>

        {status === 'none' || status === 'finished' ? (
          <button className="ps-btn ps-btn--start" onClick={handleStart} disabled={loading}>
            <Play size={15} />
            {t('startProject')}
          </button>
        ) : (
          <button className="ps-btn ps-btn--finish" onClick={handleFinish} disabled={loading}>
            <CheckCircle size={15} />
            {t('finishProject')}
          </button>
        )}
      </div>

      {/* ── Active session info ────────────────────────────────────────── */}
      {status === 'active' && recipe.active_started_at && (
        <div className="ps-active-info">
          <Clock size={13} />
          <span>{t('startedAt')}: {formatDateTime(recipe.active_started_at, language)}</span>
        </div>
      )}

      {/* ── Summary stats ─────────────────────────────────────────────── */}
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

      {/* ── Session history ────────────────────────────────────────────── */}
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
                  {!s.finished_at && (
                    <span className="ps-session-live">● {t('projectActive')}</span>
                  )}
                  {dur !== null && (
                    <span className="ps-session-dur">{formatDuration(dur, t)}</span>
                  )}
                </div>
                <div className="ps-session-times">
                  <div className="ps-time-row">
                    <Play size={10} />
                    <span>{formatDateTime(s.started_at, language)}</span>
                  </div>
                  {s.finished_at && (
                    <div className="ps-time-row">
                      <CheckCircle size={10} />
                      <span>{formatDateTime(s.finished_at, language)}</span>
                    </div>
                  )}
                </div>
                {/* Progress bar for finished sessions */}
                {dur !== null && total > 0 && (
                  <div className="ps-session-bar">
                    <div
                      className="ps-session-bar-fill"
                      style={{ width: `${Math.round((dur / total) * 100)}%` }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Clear all sessions ─────────────────────────────────────────── */}
      {sessions.length > 0 && (
        <div className="ps-clear-wrap">
          {confirmClear ? (
            <div className="ps-confirm-row">
              <span className="ps-confirm-text">{t('clearSessionsConfirm')}</span>
              <button className="ps-confirm-btn ps-confirm-btn--yes" onClick={handleClear} disabled={loading}>
                {t('clearSessionsYes')}
              </button>
              <button className="ps-confirm-btn ps-confirm-btn--no" onClick={() => setConfirmClear(false)}>
                {t('clearSessionsNo')}
              </button>
            </div>
          ) : (
            <button className="ps-clear-btn" onClick={() => setConfirmClear(true)} disabled={loading}>
              <Trash2 size={13} />
              {t('clearSessions')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
