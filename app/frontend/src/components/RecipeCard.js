/**
 * RecipeCard.js
 * Displays a single recipe as a card in the grid.
 * Shows thumbnail, name, and tags.
 */

import React, { useState } from 'react';
import { thumbnailUrl } from '../utils/api';
import './RecipeCard.css';

export default function RecipeCard({ recipe, onClick, style }) {
  const [imgError, setImgError] = useState(false);

  return (
    <button
      className="recipe-card fade-in"
      onClick={onClick}
      style={style}
      aria-label={`Open ${recipe.title}`}
    >
      {/* Thumbnail */}
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

        {/* File type badge */}
        <span className="recipe-type-badge">
          {recipe.file_type === 'pdf' ? 'PDF' : `IMG`}
        </span>
      </div>

      {/* Info */}
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
