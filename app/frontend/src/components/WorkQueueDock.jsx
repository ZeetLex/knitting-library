import React, { useState } from 'react';
import { Bot, CheckCircle2, Clock3, FileText, Loader2, PauseCircle, PlayCircle, X, XCircle } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import './WorkQueueDock.css';
import { approveSubscriptionJob } from '../utils/api';
import AIJobDiagnostics from './AIJobDiagnostics';

function statusIcon(status) {
  if (status === 'ready_to_review') return <CheckCircle2 size={16} />;
  if (status === 'finished') return <CheckCircle2 size={16} />;
  if (status === 'failed') return <XCircle size={16} />;
  if (status === 'cancelled') return <PauseCircle size={16} />;
  if (status === 'queued') return <Clock3 size={16} />;
  if (['awaiting_approval', 'blocked_auth', 'blocked_usage', 'interrupted'].includes(status)) return <PauseCircle size={16} />;
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
  if (job.status === 'ready_to_review') return t('aiJob_ready_to_review');
  if (job.status === 'queued') {
    return job.queue_position === 2 ? (t('aiJob_next') || 'Next up') : (t('aiJob_waiting') || 'Waiting');
  }
  const key = `aiJob_${job.status}`;
  const label = t(key);
  return label === key ? job.status : label;
}

export default function WorkQueueDock({
  queue,
  variant = 'desktop',
  onOpenImport,
  onOpenRecipe,
  onCancelAI,
  onDismissAI,
}) {
  const { t, user } = useApp();
  const [approving, setApproving] = useState(null);
  const [approvalError, setApprovalError] = useState('');
  const approve = async (job) => {
    let message = t('chatgptApproveConfirm').replace('{REQUESTER}', job.generated_by || '')
      .replace('{PAGES}', String(job.requested_pages || 0)).replace('{MODEL}', job.model || '')
      .replace('{CLEANUP}', job.cleanup_enabled ? t('chatgptCleanupYes') : t('chatgptCleanupNo'));
    if (job.transcription_options) {
      const cfg = job.transcription_options;
      message += `\n\n${t('transcriptionMode')}: ${t(cfg.ai_chatgpt_mode === 'formatted' ? 'transcriptionFormatted' : 'transcriptionLegacy')}`
        + `\n${t('transcriptionReasoning')}: ${t(cfg.ai_chatgpt_reasoning === 'medium' ? 'transcriptionMedium' : cfg.ai_chatgpt_reasoning === 'none' ? 'transcriptionNone' : 'transcriptionLow')}`
        + `\n${t('transcriptionImageDetail')}: ${t(cfg.ai_chatgpt_detail === 'high' ? 'transcriptionHigh' : 'transcriptionOriginal')}`
        + `\n${t('transcriptionConcurrency')}: ${cfg.ai_chatgpt_concurrency}`;
    }
    if (!window.confirm(message)) return;
    setApproving(job.id); setApprovalError('');
    try { await approveSubscriptionJob(job); }
    catch (e) { const key = `chatgptError_${e.message}`; setApprovalError(t(key) === key ? t('chatgptConnectionFailed') : t(key)); }
    finally { setApproving(null); }
  };
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
      {approvalError && <p className="status-error" role="alert">{approvalError}</p>}

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
        const complete = ['finished', 'failed', 'cancelled', 'ready_to_review'].includes(job.status);
        const waiting = ['awaiting_approval', 'blocked_auth', 'blocked_usage', 'interrupted'].includes(job.status);
        const initialView = job.status === 'ready_to_review' ? 'review' : 'text';
        return (
          <div
            key={job.id}
            className={`wq-card wq-card--ai wq-card--${job.status}`}
            role="button"
            tabIndex={0}
            onClick={() => onOpenRecipe?.(job.recipe_id, initialView)}
            onKeyDown={e => { if (e.key === 'Enter' && e.target === e.currentTarget) onOpenRecipe?.(job.recipe_id, initialView); }}
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
              {job.provider === 'chatgpt_subscription' && <span className="wq-meta">{t('chatgptUsingPlan')}</span>}
              {job.provider === 'chatgpt_subscription' && job.total_pages > 0 && <span className="wq-meta">{t('transcriptionProgress').replace('{DONE}', job.completed_pages).replace('{TOTAL}', job.total_pages)}{job.active_pages?.length > 0 ? ` · ${t('transcriptionActive')}: ${job.active_pages.join(', ')}` : ''}</span>}
              {job.provider === 'chatgpt_subscription' && complete && user?.is_admin && <AIJobDiagnostics jobId={job.id} />}
              {job.status === 'blocked_usage' && <a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>{t('chatgptManageUsage')}</a>}
              {job.error && <span className="wq-error">{job.provider === 'chatgpt_subscription'
                ? (t(`chatgptError_${job.error}`) === `chatgptError_${job.error}` ? t('chatgptConnectionFailed') : t(`chatgptError_${job.error}`)) : job.error}</span>}
              {job.can_approve && <button type="button" className="btn-secondary wq-approve" disabled={approving === job.id}
                onClick={e => { e.stopPropagation(); approve(job); }}>{t(job.status === 'awaiting_approval' ? 'chatgptApproveStart' : 'chatgptRetry')}</button>}
              <span className={`wq-progress ${complete || waiting ? 'wq-progress--done' : 'wq-progress--active'}`}><span /></span>
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
