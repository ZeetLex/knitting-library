import React, { useState } from 'react';
import { Play, CheckCircle } from 'lucide-react';
import { thumbnailUrl } from '../utils/api';
import { useApp } from '../utils/AppContext';
import './RecipeCard.css';

export default function RecipeCard({ recipe, onClick, style, selectionMode, selected, onToggleSelect }) {
  const { t } = useApp();
  const [imgError, setImgError] = useState(false);
  const status = recipe.project_status || 'none';

  const handleCardClick = () => {
    if (selectionMode) {
      // In selection mode the whole card acts as a toggle
      onToggleSelect(recipe.id);
    } else {
      onClick();
    }
  };

  const handleCheckboxClick = (e) => {
    // Prevent the click from bubbling up to handleCardClick
    e.stopPropagation();
    onToggleSelect(recipe.id);
  };

  return (
    <button
      className={[
        'recipe-card fade-in',
        status !== 'none' ? `recipe-card--${status}` : '',
        selectionMode ? 'recipe-card--selectable' : '',
        selected       ? 'recipe-card--selected'   : '',
      ].join(' ')}
      onClick={handleCardClick}
      style={style}
      aria-label={`Open ${recipe.title}`}
    >
      <div className="recipe-card-thumb">
        {recipe.thumbnail_path && !imgError ? (
          <img
            src={thumbnailUrl(recipe.id, recipe.thumbnail_version)}
            alt={recipe.title}
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="recipe-card-placeholder">
            <span>{recipe.file_type === 'pdf' ? '📄' : '🖼️'}</span>
          </div>
        )}

        {/* ── Selection checkbox — top-left of thumbnail ── */}
        {/* Always in the DOM so CSS can animate it in/out smoothly */}
        <button
          className={[
            'recipe-select-btn',
            selectionMode ? 'visible' : '',
            selected      ? 'checked' : '',
          ].join(' ')}
          onClick={handleCheckboxClick}
          aria-label={selected ? 'Deselect recipe' : 'Select recipe'}
          tabIndex={selectionMode ? 0 : -1}
        >
          {selected
            ? <CheckCircle size={16} />
            : <span className="recipe-select-circle" />
          }
        </button>

        <span className="recipe-type-badge">
          {recipe.file_type === 'pdf' ? 'PDF' : 'IMG'}
        </span>
        {status === 'active' && (
          <span className="recipe-status-badge recipe-status-badge--active">
            <Play size={10} /> {t('projectActive')}
          </span>
        )}
        {status === 'finished' && (
          <span className="recipe-status-badge recipe-status-badge--finished">
            <CheckCircle size={10} /> {t('projectFinished')}
          </span>
        )}
        {recipe.avg_score != null && (
          <span className="recipe-score-badge">
            ★ {recipe.avg_score}
          </span>
        )}
      </div>

      <div className="recipe-card-info">
        <h3 className="recipe-card-title">{recipe.title}</h3>
        {recipe.categories.length > 0 && (
          <p className="recipe-card-categories">
            {recipe.categories.join(' · ')}
          </p>
        )}
        {recipe.tags.length > 0 && (
          <div className="recipe-card-tags">
            {recipe.tags.slice(0, 3).map(tag => (
              <span key={tag} className="recipe-tag">{tag}</span>
            ))}
            {recipe.tags.length > 3 && (
              <span className="recipe-tag-more">+{recipe.tags.length - 3}</span>
            )}
          </div>
        )}
      </div>
    </button>
  );
}
