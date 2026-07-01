/**
 * StatisticsPage.js
 * Displays library-wide statistics and collection health.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Archive,
  BookOpen,
  Bot,
  CheckCircle2,
  CircleDot,
  Clock3,
  FileText,
  FolderKanban,
  Package,
  Palette,
  RotateCcw,
  Sparkles,
  Tags,
  Users,
  Wrench,
} from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchStats, resetAIStats } from '../utils/api';
import { getLanguageLocale } from '../utils/translations';
import './StatisticsPage.css';

function clampPercent(value) {
  const number = Number(value) || 0;
  return Math.max(0, Math.min(100, number));
}

function StatTile({ icon, label, value, sub, tone = 'accent' }) {
  return (
    <article className={`stats-tile stats-tile--${tone}`}>
      <div className="stats-tile-icon">{icon}</div>
      <div className="stats-tile-copy">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{sub}</small>
      </div>
    </article>
  );
}

function ProgressMetric({ label, value, detail, tone = 'accent' }) {
  const pct = clampPercent(value);
  return (
    <div className={`stats-progress stats-progress--${tone}`}>
      <div className="stats-progress-top">
        <span>{label}</span>
        <strong>{pct}%</strong>
      </div>
      <div className="stats-progress-track" aria-hidden="true">
        <span style={{ width: `${pct}%` }} />
      </div>
      <small>{detail}</small>
    </div>
  );
}

function BreakdownBar({ label, value, max, tone = 'accent' }) {
  const pct = max > 0 ? Math.max(4, (value / max) * 100) : 0;
  return (
    <div className={`stats-breakdown-row stats-breakdown-row--${tone}`}>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="stats-breakdown-track" aria-hidden="true">
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function StatisticsPage() {
  const { t, language, currencySymbol } = useApp();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [aiRange, setAiRange] = useState('all');
  const [aiResetting, setAiResetting] = useState(false);
  const locale = getLanguageLocale(language);
  const aiRanges = useMemo(() => ([
    { key: '24h', label: t('statsRange24h') || '24h' },
    { key: '7d', label: t('statsRange7d') || '7 days' },
    { key: '30d', label: t('statsRange30d') || '30 days' },
    { key: 'all', label: t('statsRangeAll') || 'All time' },
  ]), [t]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setStats(await fetchStats(aiRange));
    } catch (e) {
      console.error('Failed to load stats:', e);
    } finally {
      setLoading(false);
    }
  }, [aiRange]);

  useEffect(() => { load(); }, [load]);

  const fmtNum = useCallback((value) => (
    new Intl.NumberFormat(locale)
      .format(Number(value) || 0)
  ), [locale]);

  const fmtMoney = useCallback((value) => {
    const amount = Number(value) || 0;
    if (!amount) return `${currencySymbol}0`;
    return `${currencySymbol}${new Intl.NumberFormat(locale, {
      maximumFractionDigits: 0,
    }).format(amount)}`;
  }, [currencySymbol, locale]);

  const toolBreakdown = useMemo(() => {
    const counts = stats?.tool_categories || {};
    return [
      { key: 'needle', label: t('categoryNeedle'), value: counts.needle || 0, tone: 'blue' },
      { key: 'tool', label: t('categoryTool'), value: counts.tool || 0, tone: 'accent' },
      { key: 'notion', label: t('categoryNotion'), value: counts.notion || 0, tone: 'sage' },
      { key: 'other', label: t('categoryOther'), value: counts.other || 0, tone: 'muted' },
    ];
  }, [stats, t]);

  const maxToolCount = Math.max(1, ...toolBreakdown.map(item => item.value));
  const totalSessions = stats?.total_sessions || 0;
  const activeShare = totalSessions ? Math.round((stats.active_projects / totalSessions) * 100) : 0;
  const finishedShare = totalSessions ? Math.round((stats.finished_projects / totalSessions) * 100) : 0;
  const ai = stats?.ai || {};
  const fmtDuration = useCallback((seconds) => {
    const total = Math.round(Number(seconds) || 0);
    if (!total) return '0s';
    if (total < 60) return `${total}s`;
    return `${Math.floor(total / 60)}m ${total % 60}s`;
  }, []);
  const handleResetAIStats = useCallback(async () => {
    const label = aiRanges.find(item => item.key === aiRange)?.label || aiRange;
    const message = (t('statsResetAIConfirm') || 'Reset AI/OCR stats for {RANGE}?').replace('{RANGE}', label);
    if (!window.confirm(message)) return;
    setAiResetting(true);
    try {
      await resetAIStats(aiRange);
      await load();
    } catch (e) {
      console.error('Failed to reset AI stats:', e);
      window.alert(e.message || t('statsResetAIError') || 'Failed to reset AI stats');
    } finally {
      setAiResetting(false);
    }
  }, [aiRange, aiRanges, load, t]);

  return (
    <div className="stats-page">
      <header className="stats-hero">
        <div>
          <span className="stats-kicker">{t('statistics')}</span>
          <h1>{t('statsTitle')}</h1>
          <p>{t('statsSubLibrary')}</p>
        </div>
        <div className="stats-hero-mark" aria-hidden="true">
          <Sparkles size={24} />
        </div>
      </header>

      {loading ? (
        <div className="stats-loading">
          <div className="spinner" />
          <p>{t('loading')}</p>
        </div>
      ) : stats ? (
        <>
          <section className="stats-tile-grid" aria-label={t('statistics')}>
            <StatTile
              icon={<BookOpen size={22} />}
              label={t('statsRecipes')}
              value={fmtNum(stats.recipes)}
              sub={`${fmtNum(stats.categories)} ${t('statsCategories').toLowerCase()}`}
            />
            <StatTile
              icon={<Activity size={22} />}
              label={t('statsActive')}
              value={fmtNum(stats.active_projects)}
              sub={t('statsSubActive')}
              tone="blue"
            />
            <StatTile
              icon={<Package size={22} />}
              label={t('statsInventory')}
              value={fmtNum(stats.inventory_items)}
              sub={`${fmtNum(stats.inventory_total_quantity)} ${t('statsTotalPieces')}`}
              tone="sage"
            />
            <StatTile
              icon={<CheckCircle2 size={22} />}
              label={t('statsFinished')}
              value={fmtNum(stats.finished_projects)}
              sub={`${stats.completion_rate || 0}% ${t('statsCompletionRate')}`}
              tone="navy"
            />
          </section>

          <section className="stats-dashboard">
            <article className="stats-panel stats-panel--feature">
              <div className="stats-panel-heading">
                <div>
                  <span className="stats-panel-kicker">{t('statsProjectPulse')}</span>
                  <h2>{fmtNum(totalSessions)} {t('statsTotalSessions').toLowerCase()}</h2>
                </div>
                <div className="stats-ring" style={{ '--stats-ring-value': `${clampPercent(stats.completion_rate)}%` }}>
                  <strong>{stats.completion_rate || 0}%</strong>
                  <span>{t('statsDone')}</span>
                </div>
              </div>
              <div className="stats-split-bars">
                <ProgressMetric
                  label={t('statsActive')}
                  value={activeShare}
                  detail={`${fmtNum(stats.active_projects)} ${t('statsSubActive').toLowerCase()}`}
                  tone="blue"
                />
                <ProgressMetric
                  label={t('statsFinished')}
                  value={finishedShare}
                  detail={`${fmtNum(stats.finished_projects)} ${t('statsSubFinished').toLowerCase()}`}
                  tone="sage"
                />
              </div>
            </article>

            <article className="stats-panel">
              <div className="stats-panel-heading">
                <div>
                  <span className="stats-panel-kicker">{t('statsLibraryHealth')}</span>
                  <h2>{t('statsOrganization')}</h2>
                </div>
                <FolderKanban size={23} />
              </div>
              <div className="stats-stack">
                <ProgressMetric
                  label={t('statsCategorized')}
                  value={stats.category_coverage}
                  detail={`${fmtNum(stats.uncategorized_recipes)} ${t('statsUncategorizedRemaining')}`}
                />
                <ProgressMetric
                  label={t('statsTagged')}
                  value={stats.tag_coverage}
                  detail={`${fmtNum(stats.untagged_recipes)} ${t('statsUntaggedRemaining')}`}
                  tone="blue"
                />
              </div>
            </article>

            <article className="stats-panel stats-panel--ai">
              <div className="stats-panel-heading">
                <div>
                  <span className="stats-panel-kicker">{t('statsAI')}</span>
                  <h2>{t('statsAITextGenerated')}</h2>
                </div>
                <div className="stats-ai-actions">
                  <button
                    className="stats-icon-btn"
                    type="button"
                    onClick={handleResetAIStats}
                    disabled={aiResetting}
                    title={t('statsResetAI')}
                    aria-label={t('statsResetAI')}
                  >
                    <RotateCcw size={17} />
                  </button>
                  <Bot size={23} />
                </div>
              </div>
              <div className="stats-range-tabs" role="tablist" aria-label={t('statsAIRange')}>
                {aiRanges.map(item => (
                  <button
                    key={item.key}
                    type="button"
                    role="tab"
                    aria-selected={aiRange === item.key}
                    className={aiRange === item.key ? 'active' : ''}
                    onClick={() => setAiRange(item.key)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              {(ai.total_jobs || 0) > 0 ? (
                <>
                  <div className="stats-mini-grid">
                    <div>
                      <Sparkles size={17} />
                      <strong>{fmtNum(ai.finished_jobs)}</strong>
                      <span>{t('aiJob_finished')}</span>
                    </div>
                    <div>
                      <FileText size={17} />
                      <strong>{fmtNum(ai.generated_words)}</strong>
                      <span>{t('statsGeneratedWords')}</span>
                    </div>
                    <div>
                      <Tags size={17} />
                      <strong>{fmtNum(ai.total_tokens)}</strong>
                      <span>{t('statsTokenUse')}</span>
                    </div>
                    <div>
                      <Clock3 size={17} />
                      <strong>{fmtDuration(ai.avg_duration_seconds)}</strong>
                      <span>{t('statsAverageTime')}</span>
                    </div>
                  </div>
                  <div className="stats-ai-detail">
                    <span>{fmtNum(ai.prompt_tokens)} / {fmtNum(ai.completion_tokens)} {t('statsPromptCompletion')}</span>
                    <span>{fmtNum(ai.pages_processed)} {t('statsPagesProcessed')}</span>
                    <span>{ai.success_rate || 0}% {t('statsSuccessRate')}</span>
                    {(ai.top_model || ai.top_provider) && (
                      <span>{t('statsTopModel')}: <strong>{[ai.top_provider, ai.top_model].filter(Boolean).join(' · ')}</strong></span>
                    )}
                  </div>
                </>
              ) : (
                <p className="stats-note">{t('statsNoAIYet')}</p>
              )}
            </article>

            <article className="stats-panel">
              <div className="stats-panel-heading">
                <div>
                  <span className="stats-panel-kicker">{t('statsInventory')}</span>
                  <h2>{t('statsStashSnapshot')}</h2>
                </div>
                <Archive size={23} />
              </div>
              <div className="stats-mini-grid">
                <div>
                  <CircleDot size={17} />
                  <strong>{fmtNum(stats.yarns)}</strong>
                  <span>{t('statsYarns')}</span>
                </div>
                <div>
                  <Palette size={17} />
                  <strong>{fmtNum(stats.yarn_colours)}</strong>
                  <span>{t('statsColours')}</span>
                </div>
                <div>
                  <Package size={17} />
                  <strong>{fmtNum(stats.inventory_yarn_items)}</strong>
                  <span>{t('statsYarnStock')}</span>
                </div>
                <div>
                  <Wrench size={17} />
                  <strong>{fmtNum(stats.inventory_tool_items)}</strong>
                  <span>{t('statsTools')}</span>
                </div>
              </div>
              <div className="stats-inventory-strip">
                <span>{t('statsLowStock')}: <strong>{fmtNum(stats.inventory_low_stock)}</strong></span>
                <span>{t('statsValue')}: <strong>{fmtMoney(stats.inventory_value_estimate)}</strong></span>
              </div>
            </article>

            <article className="stats-panel">
              <div className="stats-panel-heading">
                <div>
                  <span className="stats-panel-kicker">{t('statsToolMix')}</span>
                  <h2>{t('statsToolMixTitle')}</h2>
                </div>
                <Wrench size={23} />
              </div>
              <div className="stats-breakdown">
                {toolBreakdown.map(item => (
                  <BreakdownBar
                    key={item.key}
                    label={item.label}
                    value={item.value}
                    max={maxToolCount}
                    tone={item.tone}
                  />
                ))}
              </div>
            </article>

            <article className="stats-panel stats-panel--compact">
              <div className="stats-panel-heading">
                <div>
                  <span className="stats-panel-kicker">{t('statsCatalog')}</span>
                  <h2>{t('statsRecipeMetadata')}</h2>
                </div>
                <Tags size={23} />
              </div>
              <div className="stats-list">
                <span><strong>{fmtNum(stats.categories)}</strong>{t('statsCategories')}</span>
                <span><strong>{fmtNum(stats.tags)}</strong>{t('statsTags')}</span>
                <span><strong>{fmtNum(stats.users)}</strong>{t('statsUsers')}</span>
              </div>
            </article>

            <article className="stats-panel stats-panel--compact stats-panel--quiet">
              <div className="stats-panel-heading">
                <div>
                  <span className="stats-panel-kicker">{t('statsPeople')}</span>
                  <h2>{fmtNum(stats.users)} {t('statsUsers').toLowerCase()}</h2>
                </div>
                <Users size={23} />
              </div>
              <p className="stats-note">{t('statsSubUsers')}</p>
            </article>

            <article className="stats-panel stats-panel--compact">
              <div className="stats-panel-heading">
                <div>
                  <span className="stats-panel-kicker">{t('statsPeople')}</span>
                  <h2>{t('statsMostActiveUsers')}</h2>
                </div>
                <Activity size={23} />
              </div>
              {stats.most_active_users?.length ? (
                <div className="stats-user-list">
                  {stats.most_active_users.map((item, index) => (
                    <div className="stats-user-row" key={`${item.user_id || item.username}-${index}`}>
                      <strong>{item.username || t('unknownUser')}</strong>
                      <span>{fmtNum(item.action_count)} {t('statsUserActions')}</span>
                      <small>
                        {fmtNum(item.projects_started)} {t('statsProjectsStarted')} · {fmtNum(item.projects_finished)} {t('statsProjectsFinished')} · {fmtNum(item.recipes_added)} {t('statsRecipesAdded')}
                      </small>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="stats-note">{t('statsNoUserActivity')}</p>
              )}
            </article>
          </section>
        </>
      ) : (
        <div className="stats-empty">
          <BookOpen size={30} />
          <p>{t('statsSubLibrary')}</p>
        </div>
      )}
    </div>
  );
}
