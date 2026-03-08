import React, { useState } from 'react';
import { Play, CheckCircle } from 'lucide-react';
import { thumbnailUrl } from '../utils/api';
import { useApp } from '../utils/AppContext';
import './RecipeCard.css';

export default function RecipeCard({ recipe, onClick, style }) {
  const { t } = useApp();
  const [imgError, setImgError] = useState(false);
  const status = recipe.project_status || 'none';

  return (
    <button
      className={`recipe-card fade-in ${status !== 'none' ? `recipe-card--${status}` : ''}`}
      onClick={onClick}
      style={style}
      aria-label={`Open ${recipe.title}`}
    >
      <div className="recipe-card-thumb">
        {recipe.thumbnail_path && !imgError ? (
          <img
            src={thumbnailUrl(recipe.id)}
            alt={recipe.title}
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="recipe-card-placeholder">
            <span>{recipe.file_type === 'pdf' ? '📄' : '🖼️'}</span>
          </div>
        )}
        <span className="recipe-type-badge">
          {recipe.file_type === 'pdf' ? 'PDF' : 'IMG'}
        </span>
        {/* Project status overlay badge */}
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
