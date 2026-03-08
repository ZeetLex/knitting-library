/**
 * Header.js
 * The top navigation bar that appears on every page.
 * Contains the app logo/name and the "Add Recipe" button.
 */

import React from 'react';
import { Plus } from 'lucide-react';
import './Header.css';

export default function Header({ onUploadClick, onLogoClick }) {
  return (
    <header className="header">
      <div className="header-inner">
        {/* Logo / App Name - clicking goes back to the grid */}
        <button className="header-logo" onClick={onLogoClick} aria-label="Go to library">
          <span className="header-logo-icon">🧶</span>
          <span className="header-logo-text">
            <span className="header-logo-main">Knitting</span>
            <span className="header-logo-sub">Library</span>
          </span>
        </button>

        {/* Add Recipe button */}
        <button className="header-upload-btn" onClick={onUploadClick}>
          <Plus size={18} />
          <span>Add Recipe</span>
        </button>
      </div>
    </header>
  );
}
