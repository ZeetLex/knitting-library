/**
 * CategoryManager.js
 * A small collapsible panel on the library page for managing categories.
 * Lets you add new categories and delete existing ones.
 * Lives just above the recipe grid, stays out of the way until opened.
 */

import React, { useState, useEffect } from 'react';
import { Plus, X, Tag, ChevronDown, ChevronUp } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchCategories, addCategory, deleteCategory } from '../utils/api';
import './CategoryManager.css';

export default function CategoryManager({ onCategoriesChanged }) {
  const { t } = useApp();
  const [open, setOpen]           = useState(false);
  const [categories, setCategories] = useState([]);
  const [input, setInput]         = useState('');
  const [error, setError]         = useState('');

  const load = () => {
    fetchCategories().then(setCategories).catch(console.error);
  };

  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    const name = input.trim();
    if (!name) return;
    if (categories.map(c => c.toLowerCase()).includes(name.toLowerCase())) {
      setError(t('categoryExists'));
      return;
    }
    setError('');
    try {
      await addCategory(name);
      setInput('');
      load();
      onCategoriesChanged?.();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleDelete = async (cat) => {
    try {
      await deleteCategory(cat);
      load();
      onCategoriesChanged?.();
    } catch (e) {
      console.error(e);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleAdd();
  };

  return (
    <div className={`category-manager ${open ? 'open' : ''}`}>
      {/* ── Toggle button ─────────────────────────────────── */}
      <button className="cm-toggle" onClick={() => setOpen(o => !o)}>
        <Tag size={15} />
        <span>{t('manageCategories')}</span>
        <span className="cm-count">{categories.length}</span>
        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>

      {/* ── Expanded panel ────────────────────────────────── */}
      {open && (
        <div className="cm-panel">
          {/* Add new */}
          <div className="cm-add-row">
            <input
              className="cm-input"
              value={input}
              onChange={e => { setInput(e.target.value); setError(''); }}
              onKeyDown={handleKeyDown}
              placeholder={t('newCategoryPlaceholder')}
              autoFocus
            />
            <button
              className="cm-add-btn"
              onClick={handleAdd}
              disabled={!input.trim()}
            >
              <Plus size={16} />
              {t('addCategory')}
            </button>
          </div>

          {error && <p className="cm-error">{error}</p>}

          {/* Existing categories */}
          <div className="cm-list">
            {categories.length === 0 ? (
              <p className="cm-empty">{t('noCategoriesYet')}</p>
            ) : (
              categories.map(cat => (
                <div key={cat} className="cm-tag">
                  <span>{cat}</span>
                  <button
                    className="cm-delete"
                    onClick={() => handleDelete(cat)}
                    title={t('deleteCategoryConfirm')}
                    aria-label={`${t('deleteCategoryConfirm')} ${cat}`}
                  >
                    <X size={13} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
