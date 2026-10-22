import React, { useState } from 'react';
import { useApp } from '../utils/AppContext';
import { fetchAIJobDiagnostics } from '../utils/api';

export default function AIJobDiagnostics({ jobId }) {
  const { t } = useApp();
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const show = async () => {
    setOpen(!open);
    if (data || open) return;
    try { setData(await fetchAIJobDiagnostics(jobId)); } catch { setError(true); }
  };
  const number = n => n == null ? t('transcriptionUnknown') : Number(n).toLocaleString();
  return <div className="ai-job-diagnostics" onClick={e => e.stopPropagation()}>
    <button type="button" className="btn-secondary" aria-expanded={open} onClick={show}>{t('transcriptionDiagnostics')}</button>
    {open && <div role="region" aria-label={t('transcriptionDiagnostics')}>
      {error ? <p role="alert">{t('chatgptConnectionFailed')}</p> : !data ? <p>{t('loading')}</p> : <>
        <p>{t('transcriptionTokens')}: {number(data.usage.total_tokens)} · {t('transcriptionReasoningTokens')}: {number(data.usage.reasoning_tokens)}</p>
        <div className="recipe-table-scroll"><table><thead><tr><th>{t('transcriptionPage')}</th><th>{t('transcriptionStage')}</th><th>{t('transcriptionDuration')}</th><th>{t('transcriptionFirstText')}</th><th>{t('transcriptionTokens')}</th></tr></thead>
          <tbody>{data.requests.map(row => <tr key={row.id}><td>{row.page_order}</td><td>{t(row.stage === 'scan' ? 'transcriptionScan' : 'aiCleanupWorkflow')}</td>
            <td>{row.duration_seconds == null ? t('transcriptionUnknown') : `${row.duration_seconds.toFixed(1)}s`}</td>
            <td>{row.first_text_seconds == null ? t('transcriptionUnknown') : `${row.first_text_seconds.toFixed(1)}s`}</td><td>{number(row.total_tokens)}</td></tr>)}</tbody></table></div>
      </>}
    </div>}
  </div>;
}
