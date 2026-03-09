/**
 * FeedbackModal
 *
 * Two modes:
 *  1. "submit" — shown after finishing a project. User rates 3 dimensions
 *     and writes notes, then submits.
 *  2. "view" — shown when clicking a finished session. Read-only display
 *     of all feedback left for that session (one entry per user).
 */
import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Star, CheckCircle } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import './FeedbackModal.css';

/* ── Star row: 1–6 clickable dots ─────────────────────────────────────────── */
function RatingRow({ label, sublabel, value, onChange, readOnly }) {
  return (
    <div className="fb-rating-row">
      <div className="fb-rating-label-wrap">
        <span className="fb-rating-label">{label}</span>
        {sublabel && <span className="fb-rating-sub">{sublabel}</span>}
      </div>
      <div className="fb-dots">
        {[1,2,3,4,5,6].map(n => (
          <button
            key={n}
            type="button"
            className={`fb-dot ${n <= value ? 'fb-dot--on' : ''} ${readOnly ? 'fb-dot--readonly' : ''}`}
            onClick={() => !readOnly && onChange(n)}
            aria-label={`${n}`}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Submit mode ─────────────────────────────────────────────────────────── */
function SubmitFeedback({ onSubmit, onSkip, loading }) {
  const { t } = useApp();
  const [ratings, setRatings] = useState({ recipe: 0, difficulty: 0, result: 0 });
  const [notes, setNotes]     = useState('');

  const set = (key, val) => setRatings(r => ({ ...r, [key]: val }));
  const valid = ratings.recipe > 0 && ratings.difficulty > 0 && ratings.result > 0;

  return (
    <div className="fb-body">
      <p className="fb-intro">{t('feedbackIntro')}</p>

      <div className="fb-ratings">
        <RatingRow
          label={t('feedbackRateRecipe')}
          sublabel={t('feedbackRateRecipeSub')}
          value={ratings.recipe}
          onChange={v => set('recipe', v)}
        />
        <RatingRow
          label={t('feedbackRateDifficulty')}
          sublabel={t('feedbackRateDifficultySub')}
          value={ratings.difficulty}
          onChange={v => set('difficulty', v)}
        />
        <RatingRow
          label={t('feedbackRateResult')}
          sublabel={t('feedbackRateResultSub')}
          value={ratings.result}
          onChange={v => set('result', v)}
        />
      </div>

      <div className="fb-notes-wrap">
        <label className="fb-notes-label">{t('feedbackNotes')}</label>
        <textarea
          className="fb-notes"
          rows={4}
          placeholder={t('feedbackNotesPlaceholder')}
          value={notes}
          onChange={e => setNotes(e.target.value)}
        />
      </div>

      <div className="fb-actions">
        <button className="fb-btn fb-btn--skip" onClick={onSkip} disabled={loading}>
          {t('feedbackSkip')}
        </button>
        <button
          className="fb-btn fb-btn--submit"
          onClick={() => onSubmit({ ...ratings, notes })}
          disabled={!valid || loading}
        >
          <CheckCircle size={16} />
          {t('feedbackSubmit')}
        </button>
      </div>
    </div>
  );
}

/* ── Score badge helper ────────────────────────────────────────────────────── */
function ScoreBadge({ r, d, res }) {
  const avg = ((r + d + res) / 3).toFixed(1);
  return <span className="fb-score-badge">{avg}/6</span>;
}

/* ── View mode ───────────────────────────────────────────────────────────── */
function ViewFeedback({ feedbackList }) {
  const { t } = useApp();
  if (!feedbackList || feedbackList.length === 0) {
    return <p className="fb-empty">{t('feedbackNone')}</p>;
  }
  return (
    <div className="fb-view-list">
      {feedbackList.map(fb => (
        <div key={fb.id} className="fb-view-entry">
          <div className="fb-view-header">
            <span className="fb-view-user">@{fb.username}</span>
            <ScoreBadge r={fb.rating_recipe} d={fb.rating_difficulty} res={fb.rating_result} />
          </div>
          <div className="fb-ratings fb-ratings--readonly">
            <RatingRow label={t('feedbackRateRecipe')}     value={fb.rating_recipe}     readOnly />
            <RatingRow label={t('feedbackRateDifficulty')} value={fb.rating_difficulty} readOnly />
            <RatingRow label={t('feedbackRateResult')}     value={fb.rating_result}     readOnly />
          </div>
          {fb.notes && (
            <div className="fb-view-notes">
              <span className="fb-view-notes-label">{t('feedbackNotes')}</span>
              <p className="fb-view-notes-text">{fb.notes}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ── Main export ─────────────────────────────────────────────────────────── */
export default function FeedbackModal({ mode, feedbackList, onSubmit, onSkip, onClose, loading }) {
  const { t } = useApp();

  const modal = (
    <div className="fb-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="fb-modal">
        <div className="fb-modal-header">
          <h2 className="fb-modal-title">
            {mode === 'submit' ? t('feedbackTitle') : t('feedbackViewTitle')}
          </h2>
          <button className="fb-close" onClick={onClose}><X size={20} /></button>
        </div>
        {mode === 'submit'
          ? <SubmitFeedback onSubmit={onSubmit} onSkip={onSkip} loading={loading} />
          : <ViewFeedback feedbackList={feedbackList} />
        }
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}
