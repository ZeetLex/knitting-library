import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, BookOpen, CheckCircle, Dice5,
  FolderOpen, Package, Play, Sparkles, Star,
} from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchRecipes, fetchStats, thumbnailUrl } from '../utils/api';
import { getLanguageLocale } from '../utils/translations';
import './HomePage.css';

function fmtDate(iso, language) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString(getLanguageLocale(language), {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function StatBubble({ icon, value, label }) {
  return (
    <div className="home-stat">
      <div className="home-stat-icon">{icon}</div>
      <strong>{value ?? '0'}</strong>
      <span>{label}</span>
    </div>
  );
}

function MiniRecipeCard({ recipe, mode, onOpen }) {
  const { t, language } = useApp();
  const [imgError, setImgError] = useState(false);
  const status = recipe.project_status || 'none';
  const showRating = mode === 'finished';
  const hasRating = recipe.avg_score != null;

  return (
    <button className={`home-recipe-card home-recipe-card--${mode}`} onClick={() => onOpen(recipe.id)}>
      <div className="home-recipe-thumb">
        {recipe.thumbnail_path && !imgError ? (
          <img
            src={thumbnailUrl(recipe.id, recipe.thumbnail_version)}
            alt={recipe.title}
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <span>{recipe.file_type === 'pdf' ? 'PDF' : 'IMG'}</span>
        )}
      </div>
      <div className="home-recipe-copy">
        <div className="home-recipe-meta-row">
          <span className="home-recipe-kicker">
            {mode === 'active' && <><Play size={12} /> {t('projectActive')}</>}
            {mode === 'finished' && <><CheckCircle size={12} /> {t('projectFinished')}</>}
            {mode === 'discover' && <><Sparkles size={12} /> {status === 'none' ? t('projectNone') : t('navInspiration')}</>}
          </span>
          {showRating && (
            <span className={`home-recipe-score ${hasRating ? '' : 'home-recipe-score--empty'}`}>
              <Star size={12} fill={hasRating ? 'currentColor' : 'none'} />
              {hasRating ? recipe.avg_score : t('projectNotRated')}
            </span>
          )}
        </div>
        <strong>{recipe.title}</strong>
        {recipe.categories?.length > 0 && <span>{recipe.categories.slice(0, 2).join(' · ')}</span>}
        {recipe.active_started_at && <span>{t('startedAt')}: {fmtDate(recipe.active_started_at, language)}</span>}
      </div>
    </button>
  );
}

function HomeProjectPanel({ panelKey, panel, loading, onOpenRecipe, onNavigate, onAddRecipe, onShuffle, t }) {
  const action = panelKey === 'active' ? () => onNavigate('recipes') : panelKey === 'discover' ? onShuffle : onAddRecipe;
  const actionLabel = panelKey === 'active' ? t('homeBrowseRecipes') : panelKey === 'discover' ? t('homeShuffle') : t('addRecipe');

  return (
    <section className={`home-project-column home-project-column--${panel.mode}`}>
      <div className="home-column-top">
        <div>
          <p className="home-section-kicker">{panel.title}</p>
          <h2>{panel.title}</h2>
        </div>
        {panelKey === 'discover' && (
          <button className="home-column-icon-btn" onClick={onShuffle} title={t('homeShuffle')} aria-label={t('homeShuffle')}>
            <Dice5 size={17} />
          </button>
        )}
      </div>

      <div className="home-column-list">
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => <div key={i} className="home-card-skeleton skeleton" />)
        ) : panel.items.length > 0 ? (
          panel.items.slice(0, 6).map(recipe => (
            <MiniRecipeCard
              key={recipe.id}
              recipe={recipe}
              mode={panel.mode}
              onOpen={onOpenRecipe}
            />
          ))
        ) : (
          <div className="home-empty home-empty--column">
            <FolderOpen size={28} />
            <p>{panel.empty}</p>
            <button onClick={action}>{actionLabel}</button>
          </div>
        )}
      </div>
    </section>
  );
}

export default function HomePage({ onOpenRecipe, onNavigate, onAddRecipe, workQueueDock }) {
  const { t } = useApp();
  const [stats, setStats] = useState(null);
  const [active, setActive] = useState([]);
  const [finished, setFinished] = useState([]);
  const [randomPool, setRandomPool] = useState([]);
  const [loading, setLoading] = useState(true);
  const [panel, setPanel] = useState('active');
  const [randomSeed, setRandomSeed] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [statsData, activeData, finishedData, recipesData] = await Promise.all([
        fetchStats().catch(() => null),
        fetchRecipes({ status: 'active', per_page: 12 }).catch(() => ({ recipes: [] })),
        fetchRecipes({ status: 'finished', per_page: 12 }).catch(() => ({ recipes: [] })),
        fetchRecipes({ per_page: 80 }).catch(() => ({ recipes: [] })),
      ]);
      setStats(statsData);
      setActive(activeData.recipes || []);
      setFinished(finishedData.recipes || []);
      setRandomPool(recipesData.recipes || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const discoverRecipes = useMemo(() => {
    const unfinished = randomPool.filter(r => (r.project_status || 'none') !== 'finished');
    const fallback = randomPool.filter(r => (r.project_status || 'none') === 'finished');
    const source = unfinished.length >= 3 ? unfinished : [...unfinished, ...fallback];
    return [...source]
      .sort((a, b) => {
        const av = Math.sin((a.id || '').split('').reduce((sum, ch) => sum + ch.charCodeAt(0), randomSeed));
        const bv = Math.sin((b.id || '').split('').reduce((sum, ch) => sum + ch.charCodeAt(0), randomSeed + 9));
        return av - bv;
      })
      .slice(0, 10);
  }, [randomPool, randomSeed]);

  const panels = {
    active: { title: t('homeActiveProjects'), items: active, empty: t('homeNoActive'), mode: 'active' },
    finished: { title: t('homeFinishedProjects'), items: finished, empty: t('homeNoFinished'), mode: 'finished' },
    discover: { title: t('homeDiscover'), items: discoverRecipes, empty: t('homeNoDiscover'), mode: 'discover' },
  };
  const current = panels[panel];
  const shuffleDiscover = () => setRandomSeed(s => s + 1);

  return (
    <div className="home-page">
      <section className="home-hero">
        <div className="home-brand-hero">
          <img className="home-brand-logo" src="/brand-logo.png" alt="" aria-hidden="true" />
          <div className="home-wordmark">
            <span>Knitting</span>
            <span>Library</span>
          </div>
        </div>
        <div className="home-botanical home-botanical--desktop" aria-hidden="true">
          <span className="home-stem home-stem--one" />
          <span className="home-stem home-stem--two" />
          <span className="home-leaf home-leaf--one" />
          <span className="home-leaf home-leaf--two" />
          <span className="home-leaf home-leaf--three" />
          <span className="home-bloom home-bloom--one" />
          <span className="home-bloom home-bloom--two" />
        </div>
      </section>

      <section className="home-stats" aria-label={t('statistics')}>
        <StatBubble icon={<BookOpen size={22} />} value={stats?.recipes} label={t('statsRecipes')} />
        <StatBubble icon={<Activity size={22} />} value={stats?.active_projects} label={t('statsActive')} />
        <StatBubble icon={<Package size={22} />} value={stats?.inventory_items} label={t('statsInventory')} />
        <StatBubble icon={<CheckCircle size={22} />} value={stats?.finished_projects} label={t('statsFinished')} />
      </section>

      {workQueueDock}

      <section className="home-projects">
        <div className="home-slider-top">
          <div>
            <p className="home-section-kicker">{t('homeToday')}</p>
            <h1>{current.title}</h1>
          </div>
          {panel === 'discover' && (
            <button className="home-shuffle" onClick={shuffleDiscover}>
              <Dice5 size={17} />
              <span>{t('homeShuffle')}</span>
            </button>
          )}
        </div>

        <div className="home-segmented" role="tablist" aria-label={t('homeProjectViews')}>
          {Object.keys(panels).map(key => (
            <button
              key={key}
              className={panel === key ? 'active' : ''}
              onClick={() => setPanel(key)}
            >
              {panels[key].title}
            </button>
          ))}
        </div>

        <div className="home-card-strip">
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => <div key={i} className="home-card-skeleton skeleton" />)
          ) : current.items.length > 0 ? (
            current.items.map(recipe => (
              <MiniRecipeCard
                key={recipe.id}
                recipe={recipe}
                mode={current.mode}
                onOpen={onOpenRecipe}
              />
            ))
          ) : (
            <div className="home-empty">
              <FolderOpen size={30} />
              <p>{current.empty}</p>
              <button onClick={panel === 'active' ? () => onNavigate('recipes') : onAddRecipe}>
                {panel === 'active' ? t('homeBrowseRecipes') : t('addRecipe')}
              </button>
            </div>
          )}
        </div>

        <div className="home-project-columns">
          {Object.entries(panels).map(([key, projectPanel]) => (
            <HomeProjectPanel
              key={key}
              panelKey={key}
              panel={projectPanel}
              loading={loading}
              onOpenRecipe={onOpenRecipe}
              onNavigate={onNavigate}
              onAddRecipe={onAddRecipe}
              onShuffle={shuffleDiscover}
              t={t}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
