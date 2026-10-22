import React from 'react';
import { useApp } from '../utils/AppContext';

const NONE_MODELS = new Set(['gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-6-sol', 'gpt-6-luna']);
export function supportsNoReasoning(model) { return NONE_MODELS.has(model); }

export default function TranscriptionControls({ cfg, onChange }) {
  const { t } = useApp();
  return <div className="ai-settings-card">
    <h4>{t('transcriptionProcessing')}</h4>
    <label className="form-label" htmlFor="transcription-mode">{t('transcriptionMode')}</label>
    <select id="transcription-mode" className="form-input" value={cfg.ai_chatgpt_mode || 'formatted'} onChange={e => onChange('ai_chatgpt_mode', e.target.value)}>
      <option value="formatted">{t('transcriptionFormatted')}</option><option value="legacy">{t('transcriptionLegacy')}</option>
    </select>
    <p className="settings-row-sub">{t('transcriptionOnePassHint')}</p>
    <details><summary>{t('transcriptionAdvanced')}</summary>
      <div className="form-stack" style={{ marginTop: 14 }}>
        <label className="form-label" htmlFor="transcription-reasoning">{t('transcriptionReasoning')}</label>
        <select id="transcription-reasoning" className="form-input" value={cfg.ai_chatgpt_reasoning || 'low'} onChange={e => onChange('ai_chatgpt_reasoning', e.target.value)}>
          <option value="low">{t('transcriptionLow')}</option><option value="medium">{t('transcriptionMedium')}</option>
          {supportsNoReasoning(cfg.ai_chatgpt_model) && <option value="none">{t('transcriptionNone')}</option>}
        </select>
        <label className="form-label" htmlFor="transcription-detail">{t('transcriptionImageDetail')}</label>
        <select id="transcription-detail" className="form-input" value={cfg.ai_chatgpt_detail || 'original'} onChange={e => onChange('ai_chatgpt_detail', e.target.value)}>
          <option value="original">{t('transcriptionOriginal')}</option><option value="high">{t('transcriptionHigh')}</option>
        </select>
        <label className="form-label" htmlFor="transcription-concurrency">{t('transcriptionConcurrency')}</label>
        <select id="transcription-concurrency" className="form-input" value={cfg.ai_chatgpt_concurrency || '2'} onChange={e => onChange('ai_chatgpt_concurrency', e.target.value)}>
          <option value="1">1</option><option value="2">2</option>
        </select>
        <p className="settings-row-sub">{t('transcriptionAdvancedHint')}</p>
      </div>
    </details>
  </div>;
}
