/**
 * YarnLibrary.js
 * Grid view of all yarns — same feel as the recipe library.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Search, Grid2X2, LayoutGrid, Square, Plus } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchYarns, yarnImageUrl } from '../utils/api';
import YarnUploadModal from '../components/YarnUploadModal';
import './YarnLibrary.css';

export default function YarnLibrary({ onYarnClick }) {
  const { t } = useApp();

  const GRID_SIZES = {
    small:  { icon: <Grid2X2 size={16} />,    cols: 'grid-small'  },
    medium: { icon: <LayoutGrid size={16} />, cols: 'grid-medium' },
    large:  { icon: <Square size={16} />,     cols: 'grid-large'  },
  };

  const [yarns, setYarns]         = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [search, setSearch]       = useState('');
  const [gridSize, setGridSize]   = useState('medium');
  const [uploadOpen, setUploadOpen] = useState(false);

  const loadYarns = useCallback(async () => {
    setLoading(true); setError(null);
    try { setYarns(await fetchYarns({ search })); }
    catch (e) { setError('Could not load yarns.'); }
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => {
    const t = setTimeout(loadYarns, 280);
    return () => clearTimeout(t);
  }, [loadYarns]);

  const countLabel = () => {
    if (yarns.length === 0) return t('yarnCount_zero');
    if (yarns.length === 1) return t('yarnCount_one');
    return `${yarns.length} ${t('yarnCount_other')}`;
  };

  return (
    <div className="yarn-library">
      {/* ── Toolbar ─────────────────────────────────────────────────── */}
      <div className="yarn-toolbar">
        <div className="yarn-search-wrap">
          <Search size={16} className="yarn-search-icon" />
          <input
            type="search"
            className="yarn-search"
            placeholder={`${t('search')}…`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="yarn-toolbar-right">
          <div className="yarn-grid-btns">
            {Object.entries(GRID_SIZES).map(([sz, cfg]) => (
              <button
                key={sz}
                className={`yarn-grid-btn ${gridSize === sz ? 'active' : ''}`}
                onClick={() => setGridSize(sz)}
                title={sz}
              >
                {cfg.icon}
              </button>
            ))}
          </div>
          <button className="yarn-add-btn" onClick={() => setUploadOpen(true)}>
            <Plus size={17} />
            <span>{t('addYarn')}</span>
          </button>
        </div>
      </div>

      {/* ── Count bar ───────────────────────────────────────────────── */}
      <div className="yarn-meta">
        <span className="yarn-count">{countLabel()}</span>
      </div>

      {/* ── Grid ────────────────────────────────────────────────────── */}
      {loading ? (
        <div className="yarn-grid-skeleton">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton-card" />
          ))}
        </div>
      ) : error ? (
        <div className="yarn-empty">
          <p>{error}</p>
        </div>
      ) : yarns.length === 0 ? (
        <div className="yarn-empty">
          <span className="yarn-empty-icon">🧵</span>
          <p>{search ? t('noYarnsFiltered') : t('noYarns')}</p>
          {!search && <p className="yarn-empty-hint">{t('noYarnsHint')}</p>}
          {!search && (
            <button className="yarn-add-btn" onClick={() => setUploadOpen(true)}>
              <Plus size={16} /> {t('addYarn')}
            </button>
          )}
        </div>
      ) : (
        <div className={`yarn-grid ${GRID_SIZES[gridSize].cols}`}>
          {yarns.map((yarn) => (
            <YarnCard key={yarn.id} yarn={yarn} onClick={() => onYarnClick(yarn.id)} />
          ))}
        </div>
      )}

      {/* ── Upload modal ────────────────────────────────────────────── */}
      {uploadOpen && (
        <YarnUploadModal
          onClose={() => setUploadOpen(false)}
          onSuccess={(newYarn) => {
            setUploadOpen(false);
            setYarns(prev => [newYarn, ...prev]);
          }}
        />
      )}
    </div>
  );
}

function YarnCard({ yarn, onClick }) {
  const [imgError, setImgError] = useState(false);

  return (
    <button className="yarn-card fade-in" onClick={onClick}>
      <div className="yarn-card-thumb">
        {yarn.image_path && !imgError ? (
          <img
            src={yarnImageUrl(yarn.id)}
            alt={yarn.name}
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="yarn-card-placeholder">🧵</div>
        )}
      </div>
      <div className="yarn-card-info">
        <h3 className="yarn-card-title">{yarn.name}</h3>
        {yarn.wool_type && (
          <p className="yarn-card-sub">{yarn.wool_type}</p>
        )}
        <div className="yarn-card-tags">
          {yarn.needles && <span className="yarn-chip">🪡 {yarn.needles}</span>}
          {yarn.yardage && <span className="yarn-chip">📏 {yarn.yardage}</span>}
        </div>
      </div>
    </button>
  );
}
