import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Search, SlidersHorizontal, X, Grid2X2, LayoutGrid, Square,
  Play, CheckCircle, Trash2, CheckSquare, Square as SquareIcon, Settings2, Plus,
  MousePointer2, Tag,
} from 'lucide-react';
import RecipeCard from '../components/RecipeCard';

import { useApp } from '../utils/AppContext';
import { fetchRecipes, fetchCategories, fetchAllCategories, fetchTags, deleteRecipe, addCategory, deleteCategory, bulkUpdateRecipes } from '../utils/api';
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
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError]             = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages]   = useState(1);
  const [totalCount, setTotalCount]   = useState(0);

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

  // ── Category management ───────────────────────────────────────────────────
  const [managingCats, setManagingCats]   = useState(false);
  const [allCategories, setAllCategories] = useState([]);  // all cats for manage UI
  const [newCatName, setNewCatName]       = useState('');
  const [catSaving, setCatSaving]         = useState(false);
  const [catError, setCatError]           = useState('');
  const newCatRef = useRef(null);

  // Fetch all categories (including unassigned) for the manage panel
  useEffect(() => {
    if (managingCats) {
      fetchAllCategories().then(setAllCategories).catch(console.error);
    }
  }, [managingCats]);

  const refreshCategories = useCallback(() => {
    // Refresh both the filter pills and the manage panel list
    fetchCategories().then(setCategories).catch(console.error);
    if (managingCats) {
      fetchAllCategories().then(setAllCategories).catch(console.error);
    }
  }, [managingCats]);

  const handleAddCategory = async (e) => {
    e.preventDefault();
    const name = newCatName.trim();
    if (!name) return;
    setCatSaving(true); setCatError('');
    try {
      await addCategory(name);
      setNewCatName('');
      refreshCategories();
      newCatRef.current?.focus();
    } catch (err) {
      setCatError(err.message || 'Could not add category');
    } finally {
      setCatSaving(false);
    }
  };

  const handleDeleteCategory = async (name) => {
    try {
      // If this category is currently active as a filter, clear the filter first
      if (category === name) setCategory('');
      await deleteCategory(name);
      refreshCategories();
    } catch (err) {
      setCatError(err.message || 'Could not delete category');
    }
  };

  // ── Scroll restoration ────────────────────────────────────────────────────
  const SCROLL_KEY = 'library_scroll_y';

  // Save scroll position when a recipe card is opened, then restore it on return
  const handleRecipeClick = useCallback((id) => {
    sessionStorage.setItem(SCROLL_KEY, String(window.scrollY));
    onRecipeClick(id);
  }, [onRecipeClick]);

  // Restore scroll after the recipe list has loaded and been painted
  useEffect(() => {
    if (!loading && recipes.length > 0) {
      const saved = sessionStorage.getItem(SCROLL_KEY);
      if (saved) {
        sessionStorage.removeItem(SCROLL_KEY);
        // Wait one animation frame so the grid is fully painted before scrolling
        requestAnimationFrame(() => window.scrollTo(0, parseInt(saved, 10)));
      }
    }
  }, [loading]); // intentionally omits recipes.length — only run after load completes

  // ── Selection state ───────────────────────────────────────────────────────
  // selectedIds is a Set of recipe IDs the user has ticked
  const [selectedIds, setSelectedIds]               = useState(new Set());
  const [selectionModeActive, setSelectionModeActive] = useState(false); // explicit toggle
  const [deleteConfirm, setDeleteConfirm]           = useState(false);
  const [deleting, setDeleting]                     = useState(false);

  // ── Bulk tag/category state ───────────────────────────────────────────────
  const [bulkModal, setBulkModal]     = useState(false);
  const [bulkTags, setBulkTags]       = useState('');
  const [bulkCats, setBulkCats]       = useState('');
  const [bulkApplying, setBulkApplying] = useState(false);
  const [bulkDone, setBulkDone]       = useState(false);

  // Derived: cards are selectable if the explicit toggle is on OR ≥1 card is already checked
  const selectionMode = selectionModeActive || selectedIds.size > 0;

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
    // Reset to page 1 and clear selection whenever filters change
    setCurrentPage(1);
    setSelectedIds(new Set());
    setDeleteConfirm(false);
    try {
      const data = await fetchRecipes({ search, category, tags: activeTags, status: statusFilter, page: 1 });
      setRecipes(data.recipes);
      setTotalPages(data.pages);
      setTotalCount(data.total);
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

  // ── Load more (next page, appended to existing results) ──────────────────
  const loadMore = useCallback(async () => {
    const nextPage = currentPage + 1;
    setLoadingMore(true);
    try {
      const data = await fetchRecipes({ search, category, tags: activeTags, status: statusFilter, page: nextPage });
      setRecipes(prev => [...prev, ...data.recipes]);
      setCurrentPage(nextPage);
      setTotalPages(data.pages);
      setTotalCount(data.total);
    } catch (e) {
      // Non-critical — leave existing recipes displayed
    } finally {
      setLoadingMore(false);
    }
  }, [search, category, activeTags, statusFilter, currentPage]);

  // ── Filter helpers ────────────────────────────────────────────────────────
  const toggleTag = (tag) => {
    setActiveTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]);
  };

  const clearFilters = () => { setSearch(''); setCategory(''); setActiveTags([]); setStatusFilter(''); };
  const hasActiveFilters = search || category || activeTags.length > 0 || statusFilter;

  const recipeCountLabel = () => {
    if (totalCount === 0) return t('recipeCount_zero');
    if (totalCount === 1) return t('recipeCount_one');
    return `${totalCount} ${t('recipeCount_other')}`;
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
    setSelectionModeActive(false);
    setDeleteConfirm(false);
    setBulkModal(false);
    setBulkTags('');
    setBulkCats('');
    setBulkDone(false);
  };

  const toggleSelectionMode = () => {
    if (selectionModeActive || selectedIds.size > 0) {
      clearSelection();
    } else {
      setSelectionModeActive(true);
    }
  };

  // ── Bulk apply tags/categories ────────────────────────────────────────────
  const handleBulkApply = async () => {
    const tags = bulkTags.split(',').map(s => s.trim()).filter(Boolean);
    const cats = bulkCats.split(',').map(s => s.trim()).filter(Boolean);
    if (!tags.length && !cats.length) return;
    setBulkApplying(true);
    try {
      await bulkUpdateRecipes(Array.from(selectedIds), { tags, categories: cats });
      setBulkDone(true);
      setBulkTags('');
      setBulkCats('');
      // Reload to reflect updated tags/categories on cards
      loadRecipes();
      setTimeout(() => setBulkDone(false), 2000);
    } catch (_) {
      // non-critical — leave modal open so user can retry
    } finally {
      setBulkApplying(false);
    }
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
                <div className="filter-label-row">
                  <label className="filter-label">{t('category')}</label>
                  <button
                    className={`cat-manage-btn ${managingCats ? 'active' : ''}`}
                    onClick={() => { setManagingCats(m => !m); setCatError(''); setNewCatName(''); }}
                    title={managingCats ? 'Done managing' : 'Add or remove categories'}
                  >
                    <Settings2 size={13} />
                    {managingCats ? 'Done' : 'Manage'}
                  </button>
                </div>

                {managingCats ? (
                  <div className="cat-manage-panel">
                    {catError && <p className="cat-manage-error">{catError}</p>}
                    <div className="cat-manage-pills">
                      {allCategories.length === 0 && (
                        <span className="cat-manage-empty">No categories yet</span>
                      )}
                      {allCategories.map(cat => (
                        <span key={cat} className="cat-manage-pill">
                          {cat}
                          <button
                            className="cat-manage-delete"
                            onClick={() => handleDeleteCategory(cat)}
                            title={`Delete "${cat}"`}
                            aria-label={`Delete category ${cat}`}
                          >
                            <X size={11} />
                          </button>
                        </span>
                      ))}
                    </div>
                    <form className="cat-manage-add" onSubmit={handleAddCategory}>
                      <input
                        ref={newCatRef}
                        type="text"
                        value={newCatName}
                        onChange={e => setNewCatName(e.target.value)}
                        placeholder="New category name…"
                        className="cat-manage-input"
                        disabled={catSaving}
                        maxLength={60}
                      />
                      <button type="submit" className="cat-manage-add-btn" disabled={catSaving || !newCatName.trim()}>
                        <Plus size={14} />
                      </button>
                    </form>
                  </div>
                ) : (
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
                )}
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

      {/* ── Meta row: recipe count + selection controls ── */}
      <div className="library-meta">
        {!loading && <p className="recipe-count">{recipeCountLabel()}</p>}
        {!loading && recipes.length > 0 && (
          <div className="meta-selection-btns">
            {/* Selection Mode toggle — enter click-to-select mode */}
            <button
              className={`select-mode-btn ${selectionMode ? 'active' : ''}`}
              onClick={toggleSelectionMode}
              title={selectionMode ? 'Exit selection mode' : 'Enter selection mode'}
            >
              <MousePointer2 size={15} />
              {selectionMode ? t('selectionModeOff') : t('selectionModeOn')}
            </button>
            {/* Select All — only shown while in selection mode */}
            {selectionMode && (
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
              onClick={() => handleRecipeClick(recipe.id)}
              style={{ animationDelay: `${Math.min(i * 30, 300)}ms` }}
              selectionMode={selectionMode}
              selected={selectedIds.has(recipe.id)}
              onToggleSelect={toggleSelect}
            />
          ))
        )}
      </div>

      {/* ── Load more ── */}
      {!loading && !error && currentPage < totalPages && (
        <div className="load-more-wrap">
          <button
            className="load-more-btn"
            onClick={loadMore}
            disabled={loadingMore}
          >
            {loadingMore ? t('loading') : `${t('loadMore')} (${totalCount - recipes.length} ${t('recipeCount_other')})`}
          </button>
        </div>
      )}

      {/* ── Floating selection toolbar — appears when ≥1 card is selected ── */}
      {selectionMode && (
        <div className="selection-toolbar">
          <div className="selection-toolbar-inner">
            <span className="selection-count">
              <CheckSquare size={16} />
              {selectedIds.size} {t('bulkSelected')}
            </span>

            <div className="selection-actions">
              {deleteConfirm ? (
                <>
                  <span className="selection-confirm-label">
                    {t('deleteConfirmTitle')} ({selectedIds.size}) {t('deleteConfirmText2')}
                  </span>
                  <button
                    className="selection-btn selection-btn--cancel"
                    onClick={() => setDeleteConfirm(false)}
                    disabled={deleting}
                  >
                    {t('cancel')}
                  </button>
                  <button
                    className="selection-btn selection-btn--danger"
                    onClick={handleDeleteSelected}
                    disabled={deleting}
                  >
                    {deleting ? 'Deleting…' : <><Trash2 size={14} /> {t('clearSessionsYes')}</>}
                  </button>
                </>
              ) : (
                <>
                  <button
                    className="selection-btn selection-btn--ghost"
                    onClick={clearSelection}
                  >
                    <X size={14} /> {t('cancel')}
                  </button>
                  {selectedIds.size > 0 && (
                    <button
                      className={`selection-btn selection-btn--tag ${bulkModal ? 'active' : ''}`}
                      onClick={() => { setBulkModal(m => !m); setBulkDone(false); }}
                    >
                      <Tag size={14} /> {t('bulkAddTags')}
                    </button>
                  )}
                  {selectedIds.size > 0 && (
                    <button
                      className="selection-btn selection-btn--danger"
                      onClick={handleDeleteSelected}
                    >
                      <Trash2 size={14} /> {t('delete')} ({selectedIds.size})
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          {/* ── Bulk tag/category popover ── */}
          {bulkModal && !deleteConfirm && (
            <div className="bulk-tag-panel">
              <p className="bulk-tag-hint">
                {t('bulkAddTags')} &amp; {t('bulkAddCategories')} — {t('bulkSelected')}: {selectedIds.size}
              </p>
              <div className="bulk-tag-row">
                <label className="bulk-tag-label">{t('tagsLabel')}</label>
                <input
                  className="bulk-tag-input"
                  value={bulkTags}
                  onChange={e => setBulkTags(e.target.value)}
                  placeholder={t('bulkTagsPlaceholder')}
                  disabled={bulkApplying}
                />
              </div>
              <div className="bulk-tag-row">
                <label className="bulk-tag-label">{t('category')}</label>
                <input
                  className="bulk-tag-input"
                  value={bulkCats}
                  onChange={e => setBulkCats(e.target.value)}
                  placeholder={t('bulkCatsPlaceholder')}
                  disabled={bulkApplying}
                />
              </div>
              <div className="bulk-tag-actions">
                <button
                  className="selection-btn selection-btn--ghost"
                  onClick={() => setBulkModal(false)}
                  disabled={bulkApplying}
                >
                  {t('cancel')}
                </button>
                <button
                  className="selection-btn selection-btn--primary"
                  onClick={handleBulkApply}
                  disabled={bulkApplying || (!bulkTags.trim() && !bulkCats.trim())}
                >
                  {bulkDone ? t('bulkApplied') : bulkApplying ? t('bulkApplying') : t('bulkApply')}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
