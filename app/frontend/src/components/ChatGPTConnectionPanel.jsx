import React, { useEffect, useState } from 'react';
import { Download, RefreshCw, Unplug, Upload } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchChatGPTConnection, beginChatGPTSetup, downloadChatGPTHelper, importChatGPTConnection,
  disconnectChatGPT, refreshChatGPTModels } from '../utils/api';

function saveDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ChatGPTConnectionPanel({ model, onModelChange }) {
  const { t, user } = useApp();
  const [connection, setConnection] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const translateError = (code) => {
    const translated = t(`chatgptError_${code}`);
    return translated === `chatgptError_${code}` ? `${t('chatgptConnectionFailed')} (${code})` : translated;
  };
  useEffect(() => {
    let cancelled = false;
    fetchChatGPTConnection().then(value => { if (!cancelled) setConnection(value); })
      .catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, []);
  const run = async (action) => {
    setBusy(true); setError(''); setMessage('');
    try { await action(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const setup = () => run(async () => {
    const data = await beginChatGPTSetup();
    saveDownload(new Blob([JSON.stringify(data)], { type: 'application/json' }), 'knitting-library.kl-setup');
    setStep(1);
  });
  const importFile = (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    run(async () => { setConnection(await importChatGPTConnection(file)); setStep(0); setMessage(t('chatgptConnected')); });
  };

  return <div className="ai-settings-card chatgpt-connection">
    <div className="ai-card-heading"><div><h4>{t('chatgptPlan')}</h4><p>{t('chatgptPlanDescription')}</p></div></div>
    {connection?.connected && <div className="form-stack">
      <p><strong>{t('chatgptConnected')}</strong> · {connection.email} · {t('chatgptOwner')}: {connection.owner_name}</p>
      <p className="settings-row-sub">{t('chatgptApprovalHint')}</p>
      {connection.health !== 'connected' && <p className="status-error">{t(`aiJob_${connection.health}`)}</p>}
      <div className="form-field">
        <label className="form-label" htmlFor="chatgpt-model">{t('aiModel')}</label>
        <div className="ai-model-row">
          <select id="chatgpt-model" className="form-input" value={model} onChange={e => onModelChange(e.target.value)}>
            <option value="">{t('selectModel')}</option>
            {model && !connection.models?.some(item => item.id === model) && <option value={model}>{model}</option>}
            {connection.models?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          <button type="button" className="btn-secondary" disabled={busy} aria-label={t('refreshModels')}
            onClick={() => run(async () => { const result = await refreshChatGPTModels(); setConnection(prev => ({ ...prev, models: result.models })); })}><RefreshCw size={15} /></button>
        </div>
      </div>
      <a href={connection.usage_url} target="_blank" rel="noopener noreferrer">{t('chatgptManageUsage')}</a>
      <p className="settings-row-sub">{t('chatgptUsingPlan')}</p>
    </div>}
    <div className="form-stack">
      <p>{t('chatgptSetupInstructions')}</p>
      <div className="mail-test-row">
        <button type="button" className="btn-secondary" disabled={busy || !connection?.helper_available}
          onClick={() => run(async () => saveDownload(await downloadChatGPTHelper(), 'KnittingLibrary-ChatGPT.exe'))}><Download size={15} /> {t('chatgptDownloadHelper')}</button>
        <button type="button" className="btn-secondary" disabled={busy} onClick={setup}><Download size={15} /> {t(connection?.connected ? 'chatgptReconnect' : 'chatgptDownloadSetup')}</button>
      </div>
      {connection && !connection.helper_available && <p className="status-error">{t('chatgptError_helper_unavailable')}</p>}
      {connection?.helper_sha256 && <details><summary>{t('chatgptHelperChecksum')}</summary><code style={{ overflowWrap: 'anywhere' }}>{connection.helper_sha256}</code></details>}
      {step === 1 && <p className="status-success">{t('chatgptSetupDownloaded')}</p>}
      <label className="form-label" htmlFor="chatgpt-import"><Upload size={15} /> {t('chatgptUploadConnection')}</label>
      <input id="chatgpt-import" type="file" accept=".kl-chatgpt" onChange={importFile} disabled={busy} />
      {connection?.connected && <button type="button" className="btn-secondary" disabled={busy} onClick={() => {
        if (!window.confirm(t('chatgptDisconnectConfirm'))) return;
        run(async () => { const result = await disconnectChatGPT(); setConnection({ ...result, helper_available: connection.helper_available, helper_sha256: connection.helper_sha256 });
          if (!result.revocation_confirmed) setMessage(t('chatgptRevocationUnconfirmed')); });
      }}><Unplug size={15} /> {t('chatgptDisconnect')}</button>}
    </div>
    {connection?.owner_id && connection.owner_id !== user.id && <p className="settings-row-sub">{t('chatgptOwnerTestOnly')}</p>}
    {busy && <p aria-live="polite">{t('loading')}</p>}
    {message && <p className="status-success" aria-live="polite">{message}</p>}
    {error && <p className="status-error" role="alert">{translateError(error)}</p>}
  </div>;
}
