import React from 'react';
import { Bot, CheckCircle2, Clock3, FileText, Loader2, PauseCircle, PlayCircle, X, XCircle } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import './WorkQueueDock.css';

function statusIcon(status) {
  if (status === 'finished') return <CheckCircle2 size={16} />;
  if (status === 'failed') return <XCircle size={16} />;
  if (status === 'cancelled') return <PauseCircle size={16} />;
  if (status === 'queued') return <Clock3 size={16} />;
  return <Loader2 size={16} className="wq-spin" />;
}

function parseUtcTimestamp(value) {
  if (!value) return null;
  const text = String(value);
  const iso = /[zZ]|[+-]\d\d:?\d\d$/.test(text) ? text : `${text}Z`;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatElapsed(job) {
  if (job.status === 'queued') return '';
  if (job.status !== 'running' && job.duration_seconds !== null && job.duration_seconds !== undefined) {
    const stored = Math.max(0, Math.round(Number(job.duration_seconds) || 0));
    if (stored < 60) return `${stored}s`;
    return `${Math.floor(stored / 60)}m ${stored % 60}s`;
  }
  const start = parseUtcTimestamp(job.started_at);
  if (!start) return '';
  const end = parseUtcTimestamp(job.finished_at) || new Date();
  const seconds = Math.max(0, Math.round((end.getTime() - start.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${rest}s`;
}

function statusLabel(t, job) {
  if (job.status === 'queued') {
    return job.queue_position === 2 ? (t('aiJob_next') || 'Next up') : (t('aiJob_waiting') || 'Waiting');
  }
  return t(`aiJob_${job.status}`) || job.status;
}

export default function WorkQueueDock({
  queue,
  variant = 'desktop',
  onOpenImport,
  onOpenRecipe,
  onCancelAI,
  onDismissAI,
}) {
  const { t } = useApp();
  const jobs = queue?.ai_jobs || [];
  const imports = queue?.imports || { count: 0, items: [] };
  const hasWork = jobs.length > 0 || imports.count > 0;

  if (!hasWork) return null;

  return (
    <section className={`work-queue work-queue--${variant}`} aria-label={t('workQueueTitle') || 'Work queue'}>
      <div className="work-queue-head">
        <span>{t('workQueueTitle') || 'Work queue'}</span>
        <strong>{jobs.length + (imports.count ? 1 : 0)}</strong>
      </div>

      {imports.count > 0 && (
        <button className="wq-card wq-card--import" type="button" onClick={onOpenImport}>
          <span className="wq-icon"><FileText size={16} /></span>
          <span className="wq-main">
            <span className="wq-title">{t('importWizardTitle')}</span>
            <span className="wq-meta">{imports.count} {t('importPending')}</span>
            <span className="wq-progress wq-progress--steady"><span /></span>
          </span>
          <PlayCircle size={16} className="wq-open" />
        </button>
      )}

      {jobs.map(job => {
        const complete = ['finished', 'failed', 'cancelled'].includes(job.status);
        return (
          <div
            key={job.id}
            className={`wq-card wq-card--ai wq-card--${job.status}`}
            role="button"
            tabIndex={0}
            onClick={() => onOpenRecipe?.(job.recipe_id)}
            onKeyDown={e => { if (e.key === 'Enter') onOpenRecipe?.(job.recipe_id); }}
          >
            <span className="wq-icon wq-icon--numbered">
              <Bot size={16} />
              {job.queue_position && <span className="wq-position">#{job.queue_position}</span>}
            </span>
            <span className="wq-main">
              <span className="wq-title">{job.recipe_title || t('textVersion')}</span>
              <span className="wq-meta">
                {statusIcon(job.status)}
                {statusLabel(t, job)}
                {formatElapsed(job) && <> · {formatElapsed(job)}</>}
                {job.pages_sent ? <> · {job.pages_sent} {t('aiPagesShort') || 'pages'}</> : null}
              </span>
              {job.error && <span className="wq-error">{job.error}</span>}
              <span className={`wq-progress ${complete ? 'wq-progress--done' : 'wq-progress--active'}`}><span /></span>
            </span>
            {complete ? (
              <button
                className="wq-card-action"
                type="button"
                onClick={e => { e.stopPropagation(); onDismissAI?.(job.id); }}
                aria-label={t('dismiss') || 'Dismiss'}
              >
                <X size={14} />
              </button>
            ) : (
              <button
                className="wq-card-action"
                type="button"
                onClick={e => { e.stopPropagation(); onCancelAI?.(job.id); }}
                aria-label={t('cancel')}
              >
                <X size={14} />
              </button>
            )}
          </div>
        );
      })}
    </section>
  );
}
