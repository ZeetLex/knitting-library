/**
 * YarnLibrary.js
 * Grid view of all yarns — same search/filter look as the recipe Library.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Grid2X2, LayoutGrid, Square, Plus, SlidersHorizontal, X } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchYarns, fetchYarnAutocomplete, yarnImageUrl, yarnColourImageUrl } from '../utils/api';
import YarnUploadModal from '../components/YarnUploadModal';
import CollectionToolbar from '../components/CollectionToolbar';
import './YarnLibrary.css';

const SEARCH_FIELDS = [
  { key: '',         labelKey: 'searchFieldAll'      },
  { key: 'name',     labelKey: 'searchFieldName'     },
  { key: 'material', labelKey: 'searchFieldMaterial' },
];
const AUTOCOMPLETE_FIELD = { name: 'name', material: 'wool_type' };

export default function YarnLibrary({ onYarnClick }) {
  const { t } = useApp();

  const GRID_SIZES = {
    small:  { icon: <Grid2X2 size={16} />,    cols: 'grid-small'  },
    medium: { icon: <LayoutGrid size={16} />, cols: 'grid-medium' },
    large:  { icon: <Square size={16} />,     cols: 'grid-large'  },
  };

  const [yarns, setYarns]               = useState([]);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);
  const [search, setSearch]             = useState('');
  const [searchField, setSearchField]   = useState('');
  const [suggestions, setSuggestions]   = useState([]);
  const [gridSize, setGridSize]         = useState('medium');
  const [filtersOpen, setFiltersOpen]   = useState(false);
  const [filterWoolType, setFilterWoolType]   = useState('');
  const [filterSeller, setFilterSeller]       = useState('');
  const [allWoolTypes, setAllWoolTypes] = useState([]);
  const [allSellers, setAllSellers]     = useState([]);
  const [uploadOpen, setUploadOpen]     = useState(false);

  // Load filter option lists
  useEffect(() => {
    fetchYarnAutocomplete('wool_type').then(setAllWoolTypes).catch(() => {});
    fetchYarnAutocomplete('seller').then(setAllSellers).catch(() => {});
  }, [yarns]); // refresh when yarns change so new values appear immediately

  // Load autocomplete suggestions for current search field
  useEffect(() => {
    const apiField = AUTOCOMPLETE_FIELD[searchField];
    if (!apiField) { setSuggestions([]); return; }
    fetchYarnAutocomplete(apiField).then(setSuggestions).catch(() => setSuggestions([]));
  }, [searchField]);

  const loadYarns = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      setYarns(await fetchYarns({ search, field: searchField, filterWoolType, filterSeller }));
    } catch (e) { setError('Could not load yarns.'); }
    finally { setLoading(false); }
  }, [search, searchField, filterWoolType, filterSeller]);

  useEffect(() => {
    const timer = setTimeout(loadYarns, 280);
    return () => clearTimeout(timer);
  }, [loadYarns]);

  const clearFilters = () => { setFilterWoolType(''); setFilterSeller(''); setSearch(''); setSearchField(''); };
  const hasActiveFilters = search || filterWoolType || filterSeller;

  const countLabel = () => {
    if (yarns.length === 0) return t('yarnCount_zero');
    if (yarns.length === 1) return t('yarnCount_one');
    return `${yarns.length} ${t('yarnCount_other')}`;
  };

  const currentFieldLabel = SEARCH_FIELDS.find(f => f.key === searchField)?.labelKey || 'searchFieldAll';
  const matchingSuggestions = search.length > 0
    ? suggestions.filter(s => s.toLowerCase().includes(search.toLowerCase()))
    : suggestions;
  const fieldOptions = SEARCH_FIELDS.map(field => ({ key: field.key, label: t(field.labelKey) }));

  return (
    <div className="library yarn-library">
      <CollectionToolbar
        searchValue={search}
        onSearchChange={setSearch}
        placeholder={searchField
          ? `${t('search')} ${t(currentFieldLabel).toLowerCase()}…`
          : `${t('search')}…`}
        searchLabel={`${t('search')} ${t(currentFieldLabel)}`}
        datalistId="yarn-suggestions"
        datalistOptions={matchingSuggestions}
        fieldOptions={fieldOptions}
        fieldValue={searchField}
        onFieldChange={(field) => { setSearchField(field); setSearch(''); }}
        filterButton={(
          <button
            type="button"
            className={`collection-filter-btn ${filtersOpen || (hasActiveFilters && (filterWoolType || filterSeller)) ? 'active' : ''}`}
            onClick={() => setFiltersOpen(o => !o)}
          >
            <SlidersHorizontal size={18} />
            <span>{t('yarnFilters')}</span>
            {(filterWoolType || filterSeller) && <span className="collection-filter-badge" />}
          </button>
        )}
        viewOptions={Object.entries(GRID_SIZES).map(([key, cfg]) => ({ key, label: key, icon: cfg.icon }))}
        viewValue={gridSize}
        onViewChange={setGridSize}
      >
        {filtersOpen && (
          <div className="filter-panel fade-in">
            <div className="filter-panel-inner">

              {allWoolTypes.length > 0 && (
                <div className="filter-group">
                  <label className="filter-label">{t('filterWoolType')}</label>
                  <div className="filter-pills">
                    <button className={`pill ${!filterWoolType ? 'pill-active' : ''}`} onClick={() => setFilterWoolType('')}>
                      {t('all')}
                    </button>
                    {allWoolTypes.map(w => (
                      <button
                        key={w}
                        className={`pill ${filterWoolType === w ? 'pill-active' : ''}`}
                        onClick={() => setFilterWoolType(filterWoolType === w ? '' : w)}
                      >
                        {w}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {allSellers.length > 0 && (
                <div className="filter-group">
                  <label className="filter-label">{t('filterSeller')}</label>
                  <div className="filter-pills">
                    <button className={`pill ${!filterSeller ? 'pill-active' : ''}`} onClick={() => setFilterSeller('')}>
                      {t('all')}
                    </button>
                    {allSellers.map(s => (
                      <button
                        key={s}
                        className={`pill ${filterSeller === s ? 'pill-active' : ''}`}
                        onClick={() => setFilterSeller(filterSeller === s ? '' : s)}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {hasActiveFilters && (
                <button className="clear-filters-btn" onClick={clearFilters}>
                  <X size={14} /> {t('clearFilters')}
                </button>
              )}
            </div>
          </div>
        )}
      </CollectionToolbar>

      {/* ── Count bar ───────────────────────────────────────────────── */}
      <div className="library-meta" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)', marginBottom: 0 }}>
        <p className="recipe-count">{countLabel()}</p>
      </div>

      {/* ── Grid ────────────────────────────────────────────────────── */}
      {loading ? (
        <div className={`recipe-grid ${GRID_SIZES[gridSize].cols}`}>
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="recipe-card-skeleton">
              <div className="skeleton" style={{ aspectRatio: '3/4', borderRadius: 'var(--radius)' }} />
              <div style={{ padding: '12px 0 0' }}>
                <div className="skeleton" style={{ height: 18, width: '70%', marginBottom: 8 }} />
                <div className="skeleton" style={{ height: 14, width: '50%' }} />
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="library-empty"><p className="library-empty-icon">⚠️</p><p className="library-empty-title">{error}</p></div>
      ) : yarns.length === 0 ? (
        <div className="library-empty">
          <p className="library-empty-icon">🧵</p>
          <p className="library-empty-title">{hasActiveFilters ? t('noYarnsFiltered') : t('noYarns')}</p>
          {!hasActiveFilters && <p className="library-empty-sub">{t('noYarnsHint')}</p>}
          {!hasActiveFilters && (
            <button className="library-empty-btn" onClick={() => setUploadOpen(true)}>
              <Plus size={16} /> {t('addYarn')}
            </button>
          )}
        </div>
      ) : (
        <div className={`recipe-grid ${GRID_SIZES[gridSize].cols}`}>
          {yarns.map(yarn => (
            <YarnCard key={yarn.id} yarn={yarn} onClick={() => onYarnClick(yarn.id)} />
          ))}
        </div>
      )}

      {uploadOpen && (
        <YarnUploadModal
          onClose={() => setUploadOpen(false)}
          onSuccess={(newYarn) => { setUploadOpen(false); setYarns(prev => [newYarn, ...prev]); }}
        />
      )}
    </div>
  );
}

function YarnCard({ yarn, onClick }) {
  const [imgError, setImgError] = useState(false);
  const colours = yarn.colours || [];

  return (
    <button className="recipe-card yarn-card-item fade-in" onClick={onClick}>
      <div className="recipe-card-thumb">
        {yarn.image_path && !imgError ? (
          <img src={yarnImageUrl(yarn.id)} alt={yarn.name} loading="lazy" onError={() => setImgError(true)} />
        ) : (
          <div className="recipe-card-no-thumb">🧵</div>
        )}
      </div>
      <div className="recipe-card-info">
        <h3 className="recipe-card-title">{yarn.name}</h3>
        {yarn.wool_type && <p className="recipe-card-meta">{yarn.wool_type}</p>}
        <div className="recipe-card-tags">
          {yarn.seller && <span className="recipe-tag">{yarn.seller}</span>}
          {yarn.needles && <span className="recipe-tag">🪡 {yarn.needles}</span>}
        </div>
        {/* Colour swatch strip */}
        {colours.length > 0 && (
          <div className="yarn-card-swatches">
            {colours.slice(0, 8).map(c => (
              <ColourDot key={c.id} colour={c} yarnId={yarn.id} />
            ))}
            {colours.length > 8 && (
              <span className="yarn-card-swatches-more">+{colours.length - 8}</span>
            )}
          </div>
        )}
      </div>
    </button>
  );
}

function ColourDot({ colour, yarnId }) {
  const [imgErr, setImgErr] = useState(false);
  return (
    <div className="yarn-card-swatch-dot" title={colour.name}>
      {colour.image_path && !imgErr ? (
        <img
          src={yarnColourImageUrl(yarnId, colour.id)}
          alt={colour.name}
          onError={() => setImgErr(true)}
        />
      ) : (
        <span>🎨</span>
      )}
    </div>
  );
}
