import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, Check, FolderOpen, Plus, Search, Tag, Trash2, X } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import {
  addCategory, addTag, deleteCategory, deleteTag,
  fetchCategoryDetails, fetchTagDetails,
} from '../utils/api';
import './TaxonomyManager.css';

const CONFIG = {
  category: {
    icon: FolderOpen,
    add: addCategory,
    remove: deleteCategory,
    details: fetchCategoryDetails,
    titleKey: 'manageCategoriesTitle',
    fieldKey: 'categories',
    addKey: 'addCategory',
    placeholderKey: 'newCategoryNamePlaceholder',
    searchKey: 'searchCategories',
    emptyKey: 'noCategoriesShort',
    existsKey: 'categoryExists',
    deleteTitleKey: 'deleteCategoryConfirmTitle',
  },
  tag: {
    icon: Tag,
    add: addTag,
    remove: deleteTag,
    details: fetchTagDetails,
    titleKey: 'manageTagsTitle',
    fieldKey: 'tags',
    addKey: 'addTag',
    placeholderKey: 'newTagNamePlaceholder',
    searchKey: 'searchTags',
    emptyKey: 'noTagsShort',
    existsKey: 'tagExists',
    deleteTitleKey: 'deleteTagConfirmTitle',
  },
};

function dedupe(values) {
  const seen = new Set();
  return values.filter(value => {
    const key = value.trim().toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function usageLabel(t, count) {
  if (count === 1) return t('taxonomyUsageOne') || '1 recipe';
  return (t('taxonomyUsageMany') || '{count} recipes').replace('{count}', count);
}

export function TaxonomyManagerModal({
  type = 'category',
  selected = [],
  onChange,
  onClose,
  onChanged,
  selectionEnabled = true,
}) {
  const { t } = useApp();
  const cfg = CONFIG[type] || CONFIG.category;
  const Icon = cfg.icon;
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState('');
  const [newName, setNewName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const selectedSet = useMemo(() => new Set(selected.map(v => v.toLowerCase())), [selected]);

  const load = async () => {
    setLoading(true);
    try {
      const rows = await cfg.details();
      setItems(rows);
      setError('');
    } catch (e) {
      setError(e.message || (t('taxonomyLoadFailed') || 'Could not load list'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [type]);

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return items
      .filter(item => item.name.toLowerCase().includes(normalizedQuery))
      .sort((a, b) => {
        const aSelected = selectedSet.has(a.name.toLowerCase());
        const bSelected = selectedSet.has(b.name.toLowerCase());
        if (aSelected !== bSelected) return aSelected ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
  }, [items, query, selectedSet]);

  const toggleSelected = (name) => {
    if (!selectionEnabled || !onChange) return;
    const exists = selectedSet.has(name.toLowerCase());
    onChange(exists ? selected.filter(v => v.toLowerCase() !== name.toLowerCase()) : dedupe([...selected, name]));
  };

  const addItem = async (e) => {
    e?.preventDefault();
    const name = newName.trim();
    if (!name) return;
    if (items.some(item => item.name.toLowerCase() === name.toLowerCase())) {
      setError(t(cfg.existsKey));
      return;
    }
    setSaving(true);
    try {
      await cfg.add(name);
      setNewName('');
      setQuery('');
      setError('');
      if (selectionEnabled && onChange) onChange(dedupe([...selected, name]));
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message || (t('taxonomySaveFailed') || 'Could not save'));
    } finally {
      setSaving(false);
    }
  };

  const requestDelete = (item) => {
    if (item.usage_count > 0) {
      setConfirmDelete(item);
      return;
    }
    deleteItem(item.name);
  };

  const deleteItem = async (name) => {
    setSaving(true);
    try {
      await cfg.remove(name);
      if (onChange) onChange(selected.filter(v => v.toLowerCase() !== name.toLowerCase()));
      setConfirmDelete(null);
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message || (t('taxonomyDeleteFailed') || 'Could not delete'));
    } finally {
      setSaving(false);
    }
  };

  return createPortal(
    <div className="taxonomy-overlay" onClick={onClose}>
      <div className="taxonomy-modal" onClick={e => e.stopPropagation()}>
        <div className="taxonomy-header">
          <div>
            <span className="taxonomy-title-icon"><Icon size={18} /></span>
            <h3>{t(cfg.titleKey) || t(cfg.fieldKey)}</h3>
          </div>
          <button type="button" className="taxonomy-close" onClick={onClose} aria-label={t('close')}>
            <X size={19} />
          </button>
        </div>

        <div className="taxonomy-search-row">
          <Search size={16} />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder={t(cfg.searchKey)}
            className="taxonomy-search"
          />
        </div>

        <form className="taxonomy-add-row" onSubmit={addItem}>
          <input
            value={newName}
            onChange={e => { setNewName(e.target.value); setError(''); }}
            placeholder={t(cfg.placeholderKey)}
            className="taxonomy-add-input"
            maxLength={60}
            disabled={saving}
          />
          <button type="submit" className="taxonomy-add-btn" disabled={saving || !newName.trim()}>
            <Plus size={16} />
            <span>{t(cfg.addKey)}</span>
          </button>
        </form>

        {error && <p className="taxonomy-error">{error}</p>}

        <div className="taxonomy-grid">
          {loading ? (
            <p className="taxonomy-empty">{t('loading')}</p>
          ) : filtered.length === 0 ? (
            <p className="taxonomy-empty">{t(cfg.emptyKey)}</p>
          ) : filtered.map(item => {
            const active = selectedSet.has(item.name.toLowerCase());
            return (
              <div key={item.name} className={`taxonomy-card ${active ? 'selected' : ''}`}>
                <button
                  type="button"
                  className="taxonomy-card-main"
                  onClick={() => toggleSelected(item.name)}
                  disabled={!selectionEnabled}
                >
                  <span className="taxonomy-card-name">{item.name}</span>
                  <span className="taxonomy-card-count">{usageLabel(t, item.usage_count)}</span>
                  {active && <span className="taxonomy-card-check"><Check size={14} /></span>}
                </button>
                <button
                  type="button"
                  className="taxonomy-delete"
                  onClick={() => requestDelete(item)}
                  title={t('delete')}
                  aria-label={`${t('delete')} ${item.name}`}
                  disabled={saving}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            );
          })}
        </div>

        <div className="taxonomy-footer">
          <span>{selectionEnabled ? `${selected.length} ${t('taxonomySelected') || 'selected'}` : `${items.length} ${t(cfg.fieldKey)}`}</span>
          <button type="button" className="taxonomy-done" onClick={onClose}>{t('done')}</button>
        </div>

        {confirmDelete && (
          <div className="taxonomy-confirm-overlay" onClick={() => setConfirmDelete(null)}>
            <div className="taxonomy-confirm" onClick={e => e.stopPropagation()}>
              <AlertTriangle size={24} />
              <h4>{t(cfg.deleteTitleKey) || t('delete')}</h4>
              <p>
                {(t('taxonomyDeleteInUseWarning') || '"{name}" is used by {count} recipes. Deleting it will remove it from those recipes.')
                  .replace('{name}', confirmDelete.name)
                  .replace('{count}', confirmDelete.usage_count)}
              </p>
              <div className="taxonomy-confirm-actions">
                <button type="button" className="btn-secondary" onClick={() => setConfirmDelete(null)}>{t('cancel')}</button>
                <button type="button" className="btn-danger" onClick={() => deleteItem(confirmDelete.name)} disabled={saving}>
                  {t('delete')}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}

export default function TaxonomyField({ type = 'category', label, values, onChange, onChanged }) {
  const { t } = useApp();
  const cfg = CONFIG[type] || CONFIG.category;
  const [open, setOpen] = useState(false);
  const remove = (value) => onChange(values.filter(v => v !== value));

  return (
    <div className="taxonomy-field">
      <label className="taxonomy-field-label">{label || t(cfg.fieldKey)}</label>
      <div className="taxonomy-selected-row">
        {values.length === 0 ? (
          <span className="taxonomy-selected-empty">{t('taxonomyNoneSelected') || 'None selected'}</span>
        ) : values.map(value => (
          <span key={value} className="taxonomy-selected-chip">
            {value}
            <button type="button" onClick={() => remove(value)} aria-label={`${t('remove') || 'Remove'} ${value}`}>
              <X size={13} />
            </button>
          </span>
        ))}
        <button type="button" className="taxonomy-open-btn" onClick={() => setOpen(true)}>
          <Plus size={15} />
          <span>{t(cfg.addKey)}</span>
        </button>
      </div>
      {open && (
        <TaxonomyManagerModal
          type={type}
          selected={values}
          onChange={onChange}
          onClose={() => setOpen(false)}
          onChanged={onChanged}
        />
      )}
    </div>
  );
}
