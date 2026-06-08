import React, { useState, useEffect } from 'react';
import { Plus, X, Tag, ChevronDown, ChevronUp } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { fetchCategories, addCategory, deleteCategory } from '../utils/api';
import './CategoryManager.css';

export default function CategoryManager({ onCategoriesChanged }) {
  const { t } = useApp();
  const [open, setOpen]             = useState(false);
  const [categories, setCategories] = useState([]);
  const [input, setInput]           = useState('');
  const [error, setError]           = useState('');

  // Load once on mount only — we manage the list locally after that
  useEffect(() => {
    fetchCategories().then(setCategories).catch(console.error);
  }, []);

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
      // Update local state directly so panel stays open and shows the new tag immediately
      setCategories(prev => [...prev, name]);
      // Tell parent (updates filter pills) but does NOT remount this component
      onCategoriesChanged?.();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleDelete = async (cat) => {
    try {
      await deleteCategory(cat);
      setCategories(prev => prev.filter(c => c !== cat));
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
      <button className="cm-toggle" onClick={() => setOpen(o => !o)}>
        <Tag size={15} />
        <span>{t('manageCategories')}</span>
        <span className="cm-count">{categories.length}</span>
        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>

      {open && (
        <div className="cm-panel">
          <div className="cm-add-row">
            <input
              className="cm-input"
              value={input}
              onChange={e => { setInput(e.target.value); setError(''); }}
              onKeyDown={handleKeyDown}
              placeholder={t('newCategoryPlaceholder')}
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
