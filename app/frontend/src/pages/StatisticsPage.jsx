/**
 * StatisticsPage.js
 * Displays library-wide statistics and collection health.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Archive,
  BookOpen,
  CheckCircle2,
  CircleDot,
  FolderKanban,
  Package,
  Palette,
  Sparkles,
  Tags,
  Users,
  Wrench,
} from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchStats } from '../utils/api';
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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setStats(await fetchStats());
    } catch (e) {
      console.error('Failed to load stats:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const fmtNum = useCallback((value) => (
    new Intl.NumberFormat(language === 'no' ? 'nb-NO' : language === 'hu' ? 'hu-HU' : 'en-US')
      .format(Number(value) || 0)
  ), [language]);

  const fmtMoney = useCallback((value) => {
    const amount = Number(value) || 0;
    if (!amount) return `${currencySymbol}0`;
    return `${currencySymbol}${new Intl.NumberFormat(language === 'no' ? 'nb-NO' : language === 'hu' ? 'hu-HU' : 'en-US', {
      maximumFractionDigits: 0,
    }).format(amount)}`;
  }, [currencySymbol, language]);

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
