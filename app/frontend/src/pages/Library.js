import React, { useState, useEffect, useCallback } from 'react';
import {
  Search, SlidersHorizontal, X, Grid2X2, LayoutGrid, Square,
  Play, CheckCircle, Trash2, CheckSquare, Square as SquareIcon,
} from 'lucide-react';
import RecipeCard from '../components/RecipeCard';

import { useApp } from '../utils/AppContext';
import { fetchRecipes, fetchCategories, fetchTags, deleteRecipe } from '../utils/api';
import './Library.css';

export default function Library({ refreshKey, onRecipeClick, onUploadClick }) {
  const { t } = useApp();

  const GRID_SIZES = {
    small:  { label: t('gridSmall'),  icon: <Grid2X2 size={16} />,    cols: 'grid-small'  },
    medium: { label: t('gridMedium'), icon: <LayoutGrid size={16} />, cols: 'grid-medium' },
    large:  { label: t('gridLarge'),  icon: <Square size={16} />,     cols: 'grid-large'  },
  };

  // ── Data ──────────────────────────────────────────────────────────────────
  const [recipes, setRecipes]         = useState([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);

  // ── Filters ───────────────────────────────────────────────────────────────
  const [search, setSearch]           = useState('');
  const [category, setCategory]       = useState('');
  const [activeTags, setActiveTags]   = useState([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [categories, setCategories]   = useState([]);
  const [allTags, setAllTags]         = useState([]);

  // ── UI state ──────────────────────────────────────────────────────────────
  const [gridSize, setGridSize]       = useState('medium');
  const [filtersOpen, setFiltersOpen] = useState(false);

  // ── Selection state ───────────────────────────────────────────────────────
  // selectedIds is a Set of recipe IDs the user has ticked
  const [selectedIds, setSelectedIds]     = useState(new Set());
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting]           = useState(false);

  // Derived: are we in selection mode? (any card ticked)
  const selectionMode = selectedIds.size > 0;

  // ── Load categories & tags ────────────────────────────────────────────────
  useEffect(() => {
    fetchCategories().then(setCategories).catch(console.error);
  }, [refreshKey]);

  useEffect(() => {
    fetchTags().then(setAllTags).catch(console.error);
  }, [refreshKey]);

  // ── Load recipes (debounced) ──────────────────────────────────────────────
  const loadRecipes = useCallback(async () => {
    setLoading(true);
    setError(null);
    // Clear selection whenever the visible set changes
    setSelectedIds(new Set());
    setDeleteConfirm(false);
    try {
      const data = await fetchRecipes({ search, category, tags: activeTags, status: statusFilter });
      setRecipes(data);
    } catch (e) {
      setError('Could not load recipes. Make sure the server is running.');
    } finally {
      setLoading(false);
    }
  }, [search, category, activeTags, statusFilter, refreshKey]);

  useEffect(() => {
    const timer = setTimeout(loadRecipes, 300);
    return () => clearTimeout(timer);
  }, [loadRecipes]);

  // ── Filter helpers ────────────────────────────────────────────────────────
  const toggleTag = (tag) => {
    setActiveTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]);
  };

  const clearFilters = () => { setSearch(''); setCategory(''); setActiveTags([]); setStatusFilter(''); };
  const hasActiveFilters = search || category || activeTags.length > 0 || statusFilter;

  const recipeCountLabel = () => {
    if (recipes.length === 0) return t('recipeCount_zero');
    if (recipes.length === 1) return t('recipeCount_one');
    return `${recipes.length} ${t('recipeCount_other')}`;
  };

  // ── Selection helpers ─────────────────────────────────────────────────────
  const toggleSelect = useCallback((id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
    setDeleteConfirm(false);
  }, []);

  // Select all = the IDs currently visible (after filter)
  const allFilteredIds = recipes.map(r => r.id);
  const allSelected    = allFilteredIds.length > 0 && allFilteredIds.every(id => selectedIds.has(id));

  const toggleSelectAll = () => {
    if (allSelected) {
      // Deselect everything
      setSelectedIds(new Set());
    } else {
      // Select every visible recipe
      setSelectedIds(new Set(allFilteredIds));
    }
    setDeleteConfirm(false);
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
    setDeleteConfirm(false);
  };

  // ── Mass delete ───────────────────────────────────────────────────────────
  const handleDeleteSelected = async () => {
    if (!deleteConfirm) {
      // First click → show confirmation
      setDeleteConfirm(true);
      return;
    }
    // Second click → actually delete
    setDeleting(true);
    const ids = Array.from(selectedIds);
    for (const id of ids) {
      try { await deleteRecipe(id); } catch (_) {}
    }
    setDeleting(false);
    setSelectedIds(new Set());
    setDeleteConfirm(false);
    // Reload the grid
    loadRecipes();
  };

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="library">
      {/* ── Controls bar ── */}
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
                <label className="filter-label">{t('filterAll')}</label>
                <div className="filter-pills">
                  <button
                    className={`pill ${!statusFilter ? 'pill-active' : ''}`}
                    onClick={() => setStatusFilter('')}
                  >
                    {t('filterAll')}
                  </button>
                  <button
                    className={`pill pill-status-active ${statusFilter === 'active' ? 'pill-active' : ''}`}
                    onClick={() => setStatusFilter(statusFilter === 'active' ? '' : 'active')}
                  >
                    <Play size={11} /> {t('filterActive')}
                  </button>
                  <button
                    className={`pill pill-status-finished ${statusFilter === 'finished' ? 'pill-active' : ''}`}
                    onClick={() => setStatusFilter(statusFilter === 'finished' ? '' : 'finished')}
                  >
                    <CheckCircle size={11} /> {t('filterFinished')}
                  </button>
                </div>
              </div>

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

      {/* ── Meta row: recipe count + select-all ── */}
      <div className="library-meta">
        {!loading && <p className="recipe-count">{recipeCountLabel()}</p>}
        {!loading && recipes.length > 0 && (
          <button
            className={`select-all-btn ${allSelected ? 'active' : ''}`}
            onClick={toggleSelectAll}
            title={allSelected ? 'Deselect all' : 'Select all visible'}
          >
            {allSelected
              ? <><CheckSquare size={15} /> Deselect all</>
              : <><SquareIcon  size={15} /> Select all</>
            }
          </button>
        )}
      </div>

      {/* ── Recipe grid ── */}
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
              selectionMode={selectionMode}
              selected={selectedIds.has(recipe.id)}
              onToggleSelect={toggleSelect}
            />
          ))
        )}
      </div>

      {/* ── Floating selection toolbar — appears when ≥1 card is selected ── */}
      {selectionMode && (
        <div className="selection-toolbar">
          <div className="selection-toolbar-inner">
            <span className="selection-count">
              <CheckSquare size={16} />
              {selectedIds.size} selected
            </span>

            <div className="selection-actions">
              {deleteConfirm ? (
                <>
                  <span className="selection-confirm-label">
                    Delete {selectedIds.size} {selectedIds.size === 1 ? 'recipe' : 'recipes'}? This cannot be undone.
                  </span>
                  <button
                    className="selection-btn selection-btn--cancel"
                    onClick={() => setDeleteConfirm(false)}
                    disabled={deleting}
                  >
                    Cancel
                  </button>
                  <button
                    className="selection-btn selection-btn--danger"
                    onClick={handleDeleteSelected}
                    disabled={deleting}
                  >
                    {deleting ? 'Deleting…' : <><Trash2 size={14} /> Yes, delete</>}
                  </button>
                </>
              ) : (
                <>
                  <button
                    className="selection-btn selection-btn--ghost"
                    onClick={clearSelection}
                  >
                    <X size={14} /> Cancel
                  </button>
                  <button
                    className="selection-btn selection-btn--danger"
                    onClick={handleDeleteSelected}
                  >
                    <Trash2 size={14} /> Delete {selectedIds.size}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
