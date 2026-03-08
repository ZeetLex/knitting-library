import React, { useState, useEffect, useCallback } from 'react';
import { Search, SlidersHorizontal, X, Grid2X2, LayoutGrid, Square } from 'lucide-react';
import RecipeCard from '../components/RecipeCard';
import { useApp } from '../utils/AppContext';
import { fetchRecipes, fetchCategories, fetchTags } from '../utils/api';
import './Library.css';

export default function Library({ refreshKey, onRecipeClick, onUploadClick }) {
  const { t } = useApp();

  const GRID_SIZES = {
    small:  { label: t('gridSmall'),  icon: <Grid2X2 size={16} />,    cols: 'grid-small'  },
    medium: { label: t('gridMedium'), icon: <LayoutGrid size={16} />, cols: 'grid-medium' },
    large:  { label: t('gridLarge'),  icon: <Square size={16} />,     cols: 'grid-large'  },
  };

  const [recipes, setRecipes]         = useState([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);
  const [search, setSearch]           = useState('');
  const [category, setCategory]       = useState('');
  const [activeTags, setActiveTags]   = useState([]);
  const [categories, setCategories]   = useState([]);
  const [allTags, setAllTags]         = useState([]);
  const [gridSize, setGridSize]       = useState('medium');
  const [filtersOpen, setFiltersOpen] = useState(false);

  useEffect(() => {
    fetchCategories().then(setCategories).catch(console.error);
    fetchTags().then(setAllTags).catch(console.error);
  }, [refreshKey]);

  const loadRecipes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRecipes({ search, category, tags: activeTags });
      setRecipes(data);
    } catch (e) {
      setError('Could not load recipes. Make sure the server is running.');
    } finally {
      setLoading(false);
    }
  }, [search, category, activeTags, refreshKey]);

  useEffect(() => {
    const timer = setTimeout(loadRecipes, 300);
    return () => clearTimeout(timer);
  }, [loadRecipes]);

  const toggleTag = (tag) => {
    setActiveTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]);
  };

  const clearFilters = () => { setSearch(''); setCategory(''); setActiveTags([]); };
  const hasActiveFilters = search || category || activeTags.length > 0;

  const recipeCountLabel = () => {
    if (recipes.length === 0) return t('recipeCount_zero');
    if (recipes.length === 1) return t('recipeCount_one');
    return `${recipes.length} ${t('recipeCount_other')}`;
  };

  return (
    <div className="library">
      <div className="library-controls">
        <div className="library-controls-inner">
          <div className="search-wrap">
            <Search size={18} className="search-icon" />
            <input
              type="text"
              placeholder={t('searchPlaceholder')}
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="search-input"
              aria-label={t('searchPlaceholder')}
            />
            {search && (
              <button className="search-clear" onClick={() => setSearch('')} aria-label="Clear search">
                <X size={16} />
              </button>
            )}
          </div>

          <button
            className={`filter-btn ${filtersOpen || hasActiveFilters ? 'active' : ''}`}
            onClick={() => setFiltersOpen(o => !o)}
          >
            <SlidersHorizontal size={18} />
            <span>{t('filters')}</span>
            {hasActiveFilters && <span className="filter-badge" />}
          </button>

          <div className="grid-size-switcher">
            {Object.entries(GRID_SIZES).map(([key, val]) => (
              <button
                key={key}
                className={`grid-size-btn ${gridSize === key ? 'active' : ''}`}
                onClick={() => setGridSize(key)}
                title={val.label}
              >
                {val.icon}
              </button>
            ))}
          </div>
        </div>

        {filtersOpen && (
          <div className="filter-panel fade-in">
            <div className="filter-panel-inner">
              <div className="filter-group">
                <label className="filter-label">{t('category')}</label>
                <div className="filter-pills">
                  <button className={`pill ${!category ? 'pill-active' : ''}`} onClick={() => setCategory('')}>
                    {t('all')}
                  </button>
                  {categories.map(cat => (
                    <button
                      key={cat}
                      className={`pill ${category === cat ? 'pill-active' : ''}`}
                      onClick={() => setCategory(category === cat ? '' : cat)}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              {allTags.length > 0 && (
                <div className="filter-group">
                  <label className="filter-label">{t('tags')}</label>
                  <div className="filter-pills">
                    {allTags.map(tag => (
                      <button
                        key={tag}
                        className={`pill ${activeTags.includes(tag) ? 'pill-active' : ''}`}
                        onClick={() => toggleTag(tag)}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {hasActiveFilters && (
                <button className="clear-filters-btn" onClick={clearFilters}>
                  <X size={14} />
                  {t('clearFilters')}
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="library-meta">
        {!loading && <p className="recipe-count">{recipeCountLabel()}</p>}
      </div>

      <div className={`recipe-grid ${GRID_SIZES[gridSize].cols}`}>
        {loading ? (
          Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="recipe-card-skeleton">
              <div className="skeleton" style={{ aspectRatio: '3/4', borderRadius: 'var(--radius)' }} />
              <div style={{ padding: '12px 0 0' }}>
                <div className="skeleton" style={{ height: 18, width: '70%', marginBottom: 8 }} />
                <div className="skeleton" style={{ height: 14, width: '50%' }} />
              </div>
            </div>
          ))
        ) : error ? (
          <div className="library-empty">
            <p className="library-empty-icon">⚠️</p>
            <p className="library-empty-title">{error}</p>
          </div>
        ) : recipes.length === 0 ? (
          <div className="library-empty">
            <p className="library-empty-icon">🧶</p>
            <p className="library-empty-title">
              {hasActiveFilters ? t('noRecipesFiltered') : t('noRecipes')}
            </p>
            <p className="library-empty-sub">
              {hasActiveFilters ? t('noRecipesFilteredSub') : t('noRecipesSub')}
            </p>
            {!hasActiveFilters && (
              <button className="library-empty-btn" onClick={onUploadClick}>
                {t('addFirstRecipe')}
              </button>
            )}
            {hasActiveFilters && (
              <button className="library-empty-btn secondary" onClick={clearFilters}>
                {t('clearFiltersBtn')}
              </button>
            )}
          </div>
        ) : (
          recipes.map((recipe, i) => (
            <RecipeCard
              key={recipe.id}
              recipe={recipe}
              onClick={() => onRecipeClick(recipe.id)}
              style={{ animationDelay: `${Math.min(i * 30, 300)}ms` }}
            />
          ))
        )}
      </div>
    </div>
  );
}
