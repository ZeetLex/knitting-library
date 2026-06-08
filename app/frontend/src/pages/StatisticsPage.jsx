/**
 * StatisticsPage.js
 * Displays library-wide statistics: recipe count, yarn entries, project counts, categories, tags, inventory.
 * Fetched when the page is opened (on tab change).
 */

import React, { useState, useEffect, useCallback } from 'react';
import { BarChart2, Book, Users, CheckSquare, Tag, Package, Activity, CircleDot } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchStats } from '../utils/api';
import './StatisticsPage.css';

// ── Main StatisticsPage ──
export default function StatisticsPage() {
  const { t, language, currencySymbol } = useApp();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  // Fetch stats once when the page is opened
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchStats();
      setStats(data);
    } catch (e) {
      console.error('Failed to load stats:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Helper to format numbers with thousands separator
  const fmtNum = n => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

  return (
    <div className="stats-page">
      {/* Header */}
      <div className="stats-header">
        <h1>{t('statistics')}</h1>
        <p className="stats-header-subtitle">{t('statsSubLibrary')}</p>
      </div>

      {/* Loading skeleton */}
      {loading ? (
        <div className="stats-loading">
          <div className="spinner" />
          <p>{t('loading')}</p>
        </div>
      ) : stats ? (
        // ── Stats Cards Grid ──
        <div className="stats-grid">

          {/* Recipes */}
          <StatCard
            icon={<Book size={24} />}
            title={t('statsRecipes')}
            value={fmtNum(stats.recipes)}
            sub={t('statsSubRecipes')}
            color="from-orange to-red"
          />

          {/* Yarns */}
          <StatCard
            icon={<CircleDot size={24} />}
            title={t('statsYarns')}
            value={fmtNum(stats.yarns)}
            sub={t('statsSubYarns')}
            color="from-green to-emerald"
          />

          {/* Users */}
          <StatCard
            icon={<Users size={24} />}
            title={t('statsUsers')}
            value={fmtNum(stats.users)}
            sub={t('statsSubUsers')}
            color="from-blue to-indigo"
          />

          {/* Categories */}
          <StatCard
            icon={<CheckSquare size={24} />}
            title={t('statsCategories')}
            value={fmtNum(stats.categories)}
            sub={t('statsSubCategories')}
            color="from-purple to-pink"
          />

          {/* Tags */}
          <StatCard
            icon={<Tag size={24} />}
            title={t('statsTags')}
            value={fmtNum(stats.tags)}
            sub={t('statsSubTags')}
            color="from-pink to-red"
          />

          {/* Inventory */}
          <StatCard
            icon={<Package size={24} />}
            title={t('statsInventory')}
            value={fmtNum(stats.inventory_items)}
            sub={t('statsSubInventory')}
            color="from-teal to-blue"
          />

          {/* Active Projects */}
          <StatCard
            icon={<Activity size={24} />}
            title={t('statsActive')}
            value={fmtNum(stats.active_projects)}
            sub={t('statsSubActive')}
            color="from-cyan to-blue"
          />

          {/* Finished Projects */}
          <StatCard
            icon={<BarChart2 size={24} />}
            title={t('statsFinished')}
            value={fmtNum(stats.finished_projects)}
            sub={t('statsSubFinished')}
            color="from-indigo to-purple"
          />

          {/* Total Sessions */}
          <StatCard
            icon={<Activity size={24} />}
            title={t('statsTotalSessions')}
            value={fmtNum(stats.total_sessions)}
            sub={t('statsSubTotalSessions')}
            color="from-violet to-fuchsia"
          />

        </div>
      ) : null}
    </div>
  );
}

// ── StatCard component ──
function StatCard({ icon, title, value, sub, color }) {
  return (
    <div className={`stats-card stats-card--${color}`}>
      <div className="stats-card-icon">{icon}</div>
      <div className="stats-card-title">{title}</div>
      <div className="stats-card-value">{value}</div>
      <div className="stats-card-sub">{sub}</div>
    </div>
  );
}
