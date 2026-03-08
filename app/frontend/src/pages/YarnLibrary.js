/**
 * YarnLibrary.js
 * Grid view of all yarns — same search/filter look as the recipe Library.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Search, Grid2X2, LayoutGrid, Square, Plus, ChevronDown, SlidersHorizontal, X } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchYarns, fetchYarnAutocomplete, yarnImageUrl } from '../utils/api';
import YarnUploadModal from '../components/YarnUploadModal';
import './YarnLibrary.css';

const SEARCH_FIELDS = [
  { key: '',         labelKey: 'searchFieldAll'      },
  { key: 'name',     labelKey: 'searchFieldName'     },
  { key: 'colour',   labelKey: 'searchFieldColour'   },
  { key: 'material', labelKey: 'searchFieldMaterial' },
];
const AUTOCOMPLETE_FIELD = { name: 'name', colour: 'colour', material: 'wool_type' };

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
  const [filterColour, setFilterColour]       = useState('');
  const [filterWoolType, setFilterWoolType]   = useState('');
  const [filterSeller, setFilterSeller]       = useState('');
  const [allColours, setAllColours]     = useState([]);
  const [allWoolTypes, setAllWoolTypes] = useState([]);
  const [allSellers, setAllSellers]     = useState([]);
  const [uploadOpen, setUploadOpen]     = useState(false);
  const [fieldDropdownOpen, setFieldDropdownOpen] = useState(false);
  const fieldDropdownRef = useRef(null);

  // Load filter option lists
  useEffect(() => {
    fetchYarnAutocomplete('colour').then(setAllColours).catch(() => {});
    fetchYarnAutocomplete('wool_type').then(setAllWoolTypes).catch(() => {});
    fetchYarnAutocomplete('seller').then(setAllSellers).catch(() => {});
  }, [yarns]); // refresh when yarns change so new values appear immediately

  // Load autocomplete suggestions for current search field
  useEffect(() => {
    const apiField = AUTOCOMPLETE_FIELD[searchField];
    if (!apiField) { setSuggestions([]); return; }
    fetchYarnAutocomplete(apiField).then(setSuggestions).catch(() => setSuggestions([]));
  }, [searchField]);

  // Close field dropdown on outside click
  useEffect(() => {
    const h = (e) => { if (fieldDropdownRef.current && !fieldDropdownRef.current.contains(e.target)) setFieldDropdownOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const loadYarns = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      setYarns(await fetchYarns({ search, field: searchField, filterColour, filterWoolType, filterSeller }));
    } catch (e) { setError('Could not load yarns.'); }
    finally { setLoading(false); }
  }, [search, searchField, filterColour, filterWoolType, filterSeller]);

  useEffect(() => {
    const timer = setTimeout(loadYarns, 280);
    return () => clearTimeout(timer);
  }, [loadYarns]);

  const clearFilters = () => { setFilterColour(''); setFilterWoolType(''); setFilterSeller(''); setSearch(''); setSearchField(''); };
  const hasActiveFilters = search || filterColour || filterWoolType || filterSeller;

  const countLabel = () => {
    if (yarns.length === 0) return t('yarnCount_zero');
    if (yarns.length === 1) return t('yarnCount_one');
    return `${yarns.length} ${t('yarnCount_other')}`;
  };

  const currentFieldLabel = SEARCH_FIELDS.find(f => f.key === searchField)?.labelKey || 'searchFieldAll';
  const matchingSuggestions = search.length > 0
    ? suggestions.filter(s => s.toLowerCase().includes(search.toLowerCase()))
    : suggestions;

  return (
    <div className="library yarn-library">

      {/* ── Controls bar — identical structure to recipe Library ────── */}
      <div className="library-controls">
        <div className="library-controls-inner">

          {/* Field selector + search input */}
          <div className="search-wrap yarn-search-combined">
            {/* Field dropdown pill */}
            <div className="yarn-field-selector" ref={fieldDropdownRef}>
              <button
                className="yarn-field-btn"
                onClick={() => setFieldDropdownOpen(o => !o)}
                type="button"
              >
                <span>{t(currentFieldLabel)}</span>
                <ChevronDown size={12} className={fieldDropdownOpen ? 'rotated' : ''} />
              </button>
              {fieldDropdownOpen && (
                <div className="yarn-field-dropdown">
                  {SEARCH_FIELDS.map(f => (
                    <button
                      key={f.key}
                      className={`yarn-field-option ${searchField === f.key ? 'active' : ''}`}
                      onClick={() => { setSearchField(f.key); setSearch(''); setFieldDropdownOpen(false); }}
                    >
                      {t(f.labelKey)}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Divider */}
            <span className="yarn-field-divider" />

            {/* Icon + input in their own wrapper so the icon positions relative to the input only */}
            <div className="yarn-input-wrap">
              <Search size={16} className="search-icon" />
              <input
                list="yarn-suggestions"
                type="search"
                className="search-input yarn-search-input"
                placeholder={searchField
                  ? `${t('search')} ${t(currentFieldLabel).toLowerCase()}…`
                  : `${t('search')}…`}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {matchingSuggestions.length > 0 && (
                <datalist id="yarn-suggestions">
                  {matchingSuggestions.map(s => <option key={s} value={s} />)}
                </datalist>
              )}
              {search && (
                <button className="search-clear" onClick={() => setSearch('')} aria-label="Clear">
                  <X size={16} />
                </button>
              )}
            </div>
          </div>

          {/* Filters button — same as recipe Library */}
          <button
            className={`filter-btn ${filtersOpen || (hasActiveFilters && (filterColour || filterWoolType || filterSeller)) ? 'active' : ''}`}
            onClick={() => setFiltersOpen(o => !o)}
          >
            <SlidersHorizontal size={18} />
            <span>{t('yarnFilters')}</span>
            {(filterColour || filterWoolType || filterSeller) && <span className="filter-badge" />}
          </button>

          {/* Grid size switcher — same as recipe Library */}
          <div className="grid-size-switcher">
            {Object.entries(GRID_SIZES).map(([sz, cfg]) => (
              <button
                key={sz}
                className={`grid-size-btn ${gridSize === sz ? 'active' : ''}`}
                onClick={() => setGridSize(sz)}
                title={sz}
              >
                {cfg.icon}
              </button>
            ))}
          </div>
        </div>

        {/* Filter panel */}
        {filtersOpen && (
          <div className="filter-panel fade-in">
            <div className="filter-panel-inner">

              {allColours.length > 0 && (
                <div className="filter-group">
                  <label className="filter-label">{t('filterColour')}</label>
                  <div className="filter-pills">
                    <button className={`pill ${!filterColour ? 'pill-active' : ''}`} onClick={() => setFilterColour('')}>
                      {t('all')}
                    </button>
                    {allColours.map(c => (
                      <button
                        key={c}
                        className={`pill ${filterColour === c ? 'pill-active' : ''}`}
                        onClick={() => setFilterColour(filterColour === c ? '' : c)}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                </div>
              )}

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
      </div>

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

  return (
    <button className="recipe-card yarn-card-item fade-in" onClick={onClick}>
      <div className="recipe-card-thumb">
        {yarn.image_path && !imgError ? (
          <img src={yarnImageUrl(yarn.id)} alt={yarn.name} loading="lazy" onError={() => setImgError(true)} />
        ) : (
          <div className="recipe-card-no-thumb">🧵</div>
        )}
        {yarn.colour && <span className="yarn-colour-badge">{yarn.colour}</span>}
      </div>
      <div className="recipe-card-info">
        <h3 className="recipe-card-title">{yarn.name}</h3>
        {yarn.wool_type && <p className="recipe-card-meta">{yarn.wool_type}</p>}
        <div className="recipe-card-tags">
          {yarn.seller && <span className="recipe-tag">{yarn.seller}</span>}
          {yarn.needles && <span className="recipe-tag">🪡 {yarn.needles}</span>}
        </div>
      </div>
    </button>
  );
}
