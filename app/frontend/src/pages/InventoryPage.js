/**
 * InventoryPage.js
 * Shows all inventory items (yarn skeins + tools/needles/notions).
 * Users can add, edit, adjust quantity, and view history per item.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Minus, Package, Pencil, Trash2, Clock, ChevronDown, ChevronUp, X, Search } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import {
  fetchInventory, createInventoryItem, updateInventoryItem,
  adjustInventory, deleteInventoryItem, fetchInventoryLog,
  fetchYarns, yarnColourImageUrl, yarnImageUrl
} from '../utils/api';
import './InventoryPage.css';

const TOOL_CATEGORIES = ['needle', 'tool', 'notion', 'other'];

// ── Helper: format date ───────────────────────────────────────────────────────
function fmtDate(iso, lang) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(lang === 'no' ? 'nb-NO' : 'en-US', {
    year: 'numeric', month: 'short', day: 'numeric'
  });
}

function logReasonLabel(reason, t) {
  if (reason === 'project_start') return t('logReasonProjectStart');
  if (reason === 'added')         return t('logReasonAdded');
  if (reason === 'adjustment')    return t('logReasonAdjustment');
  return t('logReasonManual');
}

// ── Inventory item card ───────────────────────────────────────────────────────
function InventoryCard({ item, onAdjust, onEdit, onDelete, t, language }) {
  const [showLog, setShowLog]   = useState(false);
  const [log, setLog]           = useState([]);
  const [logLoading, setLogLoading] = useState(false);
  const [imgErr, setImgErr]     = useState(false);

  const loadLog = async () => {
    if (showLog) { setShowLog(false); return; }
    setLogLoading(true);
    try {
      const rows = await fetchInventoryLog(item.id);
      setLog(rows);
    } catch {}
    setLogLoading(false);
    setShowLog(true);
  };

  const isYarn = item.type === 'yarn';
  const thumbSrc = isYarn && item.yarn_colour_id && item.colour_image_path
    ? yarnColourImageUrl(item.yarn_id, item.yarn_colour_id)
    : isYarn && item.yarn_id ? yarnImageUrl(item.yarn_id)
    : null;

  return (
    <div className={`inv-card ${item.quantity === 0 ? 'inv-card--empty' : ''}`}>
      {/* Thumb */}
      <div className="inv-card-thumb">
        {thumbSrc && !imgErr ? (
          <img src={thumbSrc} alt={item.name} onError={() => setImgErr(true)} />
        ) : (
          <span className="inv-card-thumb-emoji">{isYarn ? '🧵' : '🪡'}</span>
        )}
      </div>

      {/* Info */}
      <div className="inv-card-body">
        <div className="inv-card-top">
          <div className="inv-card-names">
            <span className="inv-card-name">{item.name}</span>
            {isYarn && item.colour_name && (
              <span className="inv-card-colour">{item.colour_name}</span>
            )}
            {!isYarn && item.category && (
              <span className="inv-card-category">{t('category' + item.category.charAt(0).toUpperCase() + item.category.slice(1)) || item.category}</span>
            )}
          </div>
          <div className="inv-card-actions">
            <button className="inv-icon-btn" onClick={() => onEdit(item)} title={t('edit')}><Pencil size={14} /></button>
            <button className="inv-icon-btn danger" onClick={() => onDelete(item.id)} title={t('delete')}><Trash2 size={14} /></button>
          </div>
        </div>

        {/* Quantity row */}
        <div className="inv-qty-row">
          <button className="inv-qty-btn" onClick={() => onAdjust(item, -1)} disabled={item.quantity <= 0}>
            <Minus size={14} />
          </button>
          <span className={`inv-qty-value ${item.quantity === 0 ? 'inv-qty-zero' : ''}`}>
            {item.quantity}
            <span className="inv-qty-unit">{isYarn ? t('skeinCount') : 'stk'}</span>
          </span>
          <button className="inv-qty-btn" onClick={() => onAdjust(item, 1)}>
            <Plus size={14} />
          </button>
        </div>

        {/* Purchase info */}
        {(item.purchase_price || item.purchase_date) && (
          <div className="inv-purchase-row">
            {item.purchase_price && <span>💰 {item.purchase_price}</span>}
            {item.purchase_date  && <span>📅 {fmtDate(item.purchase_date, language)}</span>}
          </div>
        )}
        {item.notes && <p className="inv-card-notes">{item.notes}</p>}

        {/* History toggle */}
        <button className="inv-log-toggle" onClick={loadLog}>
          <Clock size={12} />
          {t('inventoryLog')}
          {showLog ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>

        {showLog && (
          <div className="inv-log">
            {logLoading ? (
              <div className="inv-log-loading"><div className="yp-spinner" /></div>
            ) : log.length === 0 ? (
              <p className="inv-log-empty">{t('logEmpty')}</p>
            ) : (
              log.map(entry => (
                <div key={entry.id} className={`inv-log-row ${entry.change > 0 ? 'pos' : 'neg'}`}>
                  <span className="inv-log-change">{entry.change > 0 ? '+' : ''}{entry.change}</span>
                  <div className="inv-log-detail">
                    <span className="inv-log-reason">
                      {logReasonLabel(entry.reason, t)}
                      {entry.recipe_title ? ` — ${entry.recipe_title}` : ''}
                      {entry.note && entry.reason === 'added' ? '' : entry.note ? ` (${entry.note})` : ''}
                    </span>
                    <span className="inv-log-date">{fmtDate(entry.created_at, language)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Add/Edit modal ────────────────────────────────────────────────────────────
function InventoryModal({ editItem, initialType = 'yarn', onClose, onSaved, t, language }) {
  const isEdit = !!editItem;
  const [itemType, setItemType]     = useState(editItem?.type || initialType);
  const [name, setName]             = useState(editItem?.name || '');
  const [quantity, setQuantity]     = useState(editItem?.quantity ?? 1);
  const [category, setCategory]     = useState(editItem?.category || 'needle');
  const [purchaseDate, setPurchaseDate] = useState(editItem?.purchase_date || '');
  const [purchasePrice, setPurchasePrice] = useState(editItem?.purchase_price || '');
  const [purchaseNote, setPurchaseNote]   = useState(editItem?.purchase_note || '');
  const [notes, setNotes]           = useState(editItem?.notes || '');
  // yarn linking
  const [yarns, setYarns]           = useState([]);
  const [yarnSearch, setYarnSearch] = useState('');
  const [selectedYarn, setSelectedYarn] = useState(null);
  const [selectedColour, setSelectedColour] = useState(null);
  const [saving, setSaving]         = useState(false);
  const [error, setError]           = useState('');

  useEffect(() => {
    if (itemType === 'yarn') {
      fetchYarns().then(setYarns).catch(() => {});
    }
  }, [itemType]);

  // Pre-fill yarn/colour when editing
  useEffect(() => {
    if (editItem?.yarn_id && yarns.length > 0) {
      const y = yarns.find(y => y.id === editItem.yarn_id);
      if (y) {
        setSelectedYarn(y);
        if (editItem.yarn_colour_id) {
          const c = (y.colours || []).find(c => c.id === editItem.yarn_colour_id);
          if (c) setSelectedColour(c);
        }
      }
    }
  }, [editItem, yarns]);

  const filteredYarns = yarns.filter(y =>
    !yarnSearch || y.name.toLowerCase().includes(yarnSearch.toLowerCase())
  );

  const handleSave = async () => {
    if (!name.trim() && !(itemType === 'yarn' && selectedYarn)) {
      setError(t('inventoryItemName') + ' is required'); return;
    }
    setSaving(true); setError('');
    try {
      const finalName = itemType === 'yarn' && selectedYarn
        ? (selectedColour ? `${selectedYarn.name} — ${selectedColour.name}` : selectedYarn.name)
        : name.trim();

      const data = {
        type: itemType,
        name: finalName,
        quantity: isEdit ? undefined : Number(quantity),
        category: itemType === 'tool' ? category : '',
        yarn_id: itemType === 'yarn' && selectedYarn ? selectedYarn.id : null,
        yarn_colour_id: itemType === 'yarn' && selectedColour ? selectedColour.id : null,
        purchase_date:  purchaseDate,
        purchase_price: purchasePrice,
        purchase_note:  purchaseNote,
        notes,
      };
      let result;
      if (isEdit) {
        result = await updateInventoryItem(editItem.id, data);
      } else {
        result = await createInventoryItem(data);
      }
      onSaved(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="inv-modal">
        <div className="inv-modal-header">
          <h2>{isEdit ? t('edit') : (itemType === 'yarn' ? t('addYarnToInventory') : t('addToolToInventory'))}</h2>
          <button className="inv-modal-close" onClick={onClose}><X size={20} /></button>
        </div>

        {/* Type toggle — only on add */}
        {!isEdit && (
          <div className="inv-type-toggle">
            <button className={`inv-type-btn ${itemType === 'yarn' ? 'active' : ''}`} onClick={() => setItemType('yarn')}>
              🧵 {t('addYarnToInventory')}
            </button>
            <button className={`inv-type-btn ${itemType === 'tool' ? 'active' : ''}`} onClick={() => setItemType('tool')}>
              🪡 {t('addToolToInventory')}
            </button>
          </div>
        )}

        <div className="inv-modal-body">

          {/* ── Yarn type: search yarn database ── */}
          {itemType === 'yarn' && (
            <div className="inv-field">
              <label className="inv-label">{t('selectYarnFromDatabase')}</label>
              <div className="inv-yarn-search-wrap">
                <Search size={14} className="inv-yarn-search-icon" />
                <input
                  type="search"
                  className="inv-yarn-search"
                  placeholder={`${t('search')}…`}
                  value={yarnSearch}
                  onChange={e => { setYarnSearch(e.target.value); setSelectedYarn(null); setSelectedColour(null); }}
                />
              </div>
              {/* Yarn list */}
              <div className="inv-yarn-list">
                {filteredYarns.map(y => (
                  <YarnPickRow
                    key={y.id}
                    yarn={y}
                    selected={selectedYarn?.id === y.id}
                    selectedColour={selectedYarn?.id === y.id ? selectedColour : null}
                    onSelect={() => { setSelectedYarn(y); setSelectedColour(null); setName(''); }}
                    onSelectColour={c => setSelectedColour(c)}
                    t={t}
                  />
                ))}
              </div>
              {/* Manual name fallback */}
              <p className="inv-or-label">{t('orAddManually')}</p>
              <input
                type="text"
                className="inv-input"
                placeholder={t('inventoryItemName')}
                value={name}
                onChange={e => { setName(e.target.value); setSelectedYarn(null); setSelectedColour(null); }}
              />
            </div>
          )}

          {/* ── Tool type ── */}
          {itemType === 'tool' && (
            <>
              <div className="inv-field">
                <label className="inv-label">{t('inventoryItemName')}</label>
                <input type="text" className="inv-input" value={name} onChange={e => setName(e.target.value)} />
              </div>
              <div className="inv-field">
                <label className="inv-label">{t('inventoryCategory')}</label>
                <div className="inv-category-pills">
                  {TOOL_CATEGORIES.map(c => (
                    <button
                      key={c}
                      className={`inv-cat-pill ${category === c ? 'active' : ''}`}
                      onClick={() => setCategory(c)}
                    >
                      {t('category' + c.charAt(0).toUpperCase() + c.slice(1)) || c}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Quantity — only on create */}
          {!isEdit && (
            <div className="inv-field">
              <label className="inv-label">{t('inventoryQuantity')}</label>
              <div className="inv-qty-input-row">
                <button className="inv-qty-btn" onClick={() => setQuantity(q => Math.max(0, q - 1))}><Minus size={14} /></button>
                <input
                  type="number"
                  min="0"
                  className="inv-qty-input"
                  value={quantity}
                  onChange={e => setQuantity(Math.max(0, parseInt(e.target.value) || 0))}
                />
                <button className="inv-qty-btn" onClick={() => setQuantity(q => q + 1)}><Plus size={14} /></button>
              </div>
            </div>
          )}

          {/* Purchase info */}
          <div className="inv-field-row">
            <div className="inv-field">
              <label className="inv-label">{t('purchaseDate')}</label>
              <input type="date" className="inv-input" value={purchaseDate} onChange={e => setPurchaseDate(e.target.value)} />
            </div>
            <div className="inv-field">
              <label className="inv-label">{t('purchasePrice')}</label>
              <input type="text" className="inv-input" placeholder="e.g. 69 NOK" value={purchasePrice} onChange={e => setPurchasePrice(e.target.value)} />
            </div>
          </div>
          <div className="inv-field">
            <label className="inv-label">{t('purchaseNote')}</label>
            <input type="text" className="inv-input" placeholder={t('purchaseNote')} value={purchaseNote} onChange={e => setPurchaseNote(e.target.value)} />
          </div>
          <div className="inv-field">
            <label className="inv-label">{t('inventoryNotes')}</label>
            <textarea className="inv-input inv-textarea" rows={2} value={notes} onChange={e => setNotes(e.target.value)} />
          </div>

          {error && <p className="inv-error">{error}</p>}
        </div>

        <div className="inv-modal-footer">
          <button className="inv-modal-cancel" onClick={onClose}>{t('cancel')}</button>
          <button className="inv-modal-save" onClick={handleSave} disabled={saving}>
            {saving ? '…' : t('save')}
          </button>
        </div>
      </div>
    </div>
  );
}

function YarnPickRow({ yarn, selected, selectedColour, onSelect, onSelectColour, t }) {
  const [imgErr, setImgErr] = useState(false);
  const colours = yarn.colours || [];

  return (
    <div className={`inv-yarn-row ${selected ? 'inv-yarn-row--selected' : ''}`}>
      <button className="inv-yarn-row-main" onClick={onSelect}>
        <div className="inv-yarn-row-thumb">
          {yarn.image_path && !imgErr
            ? <img src={yarnImageUrl(yarn.id)} alt={yarn.name} onError={() => setImgErr(true)} />
            : <span>🧵</span>
          }
        </div>
        <div className="inv-yarn-row-info">
          <span className="inv-yarn-row-name">{yarn.name}</span>
          {yarn.wool_type && <span className="inv-yarn-row-sub">{yarn.wool_type}</span>}
        </div>
        {selected && <span className="inv-yarn-row-check">✓</span>}
      </button>

      {/* Colour strip — shown when this yarn is selected */}
      {selected && colours.length > 0 && (
        <div className="inv-yarn-colour-strip">
          {colours.map(c => (
            <ColourChip
              key={c.id}
              colour={c}
              yarnId={yarn.id}
              selected={selectedColour?.id === c.id}
              onSelect={() => onSelectColour(selectedColour?.id === c.id ? null : c)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ColourChip({ colour, yarnId, selected, onSelect }) {
  const [imgErr, setImgErr] = useState(false);
  return (
    <button className={`inv-colour-chip ${selected ? 'inv-colour-chip--selected' : ''}`} onClick={onSelect} title={colour.name}>
      <div className="inv-colour-chip-thumb">
        {colour.image_path && !imgErr
          ? <img src={yarnColourImageUrl(yarnId, colour.id)} alt={colour.name} onError={() => setImgErr(true)} />
          : <span>🎨</span>
        }
      </div>
      <span className="inv-colour-chip-name">{colour.name}</span>
      {selected && <span className="inv-colour-chip-check">✓</span>}
    </button>
  );
}

// ── Main InventoryPage ────────────────────────────────────────────────────────
export default function InventoryPage({ onRequestAddYarn }) {
  const { t, language } = useApp();
  const [items, setItems]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [modalOpen, setModalOpen]   = useState(false);
  const [modalInitialType, setModalInitialType] = useState('yarn'); // 'yarn' or 'tool'
  const [editItem, setEditItem]     = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const openAdd = (type = 'yarn') => { setEditItem(null); setModalInitialType(type); setModalOpen(true); };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchInventory({ type: typeFilter, search });
      setItems(data);
    } catch {}
    setLoading(false);
  }, [typeFilter, search]);

  useEffect(() => { load(); }, [load]);

  const handleAdjust = async (item, change) => {
    try {
      const updated = await adjustInventory(item.id, change, change > 0 ? 'added' : 'manual');
      setItems(prev => prev.map(i => i.id === updated.id ? updated : i));
    } catch (e) { alert(e.message); }
  };

  const handleSaved = (item) => {
    setModalOpen(false);
    setEditItem(null);
    load();
  };

  const handleDelete = async (id) => {
    try {
      await deleteInventoryItem(id);
      setItems(prev => prev.filter(i => i.id !== id));
    } catch (e) { alert(e.message); }
    setConfirmDelete(null);
  };

  const yarnItems = items.filter(i => i.type === 'yarn');
  const toolItems = items.filter(i => i.type === 'tool');

  return (
    <div className="inv-page">
      {/* ── Toolbar — single row matching YarnLibrary style ── */}
      <div className="inv-toolbar">
        <div className="inv-toolbar-top">
          <div className="inv-search-wrap">
            <Search size={15} className="inv-search-icon" />
            <input
              type="search"
              className="inv-search"
              placeholder={`${t('search')}…`}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <div className="inv-toolbar-actions">
            <button className={`inv-pill ${typeFilter==='' ? 'inv-pill--active' : ''}`} onClick={() => setTypeFilter('')}>{t('all')}</button>
            <button className={`inv-pill ${typeFilter==='yarn' ? 'inv-pill--active' : ''}`} onClick={() => setTypeFilter('yarn')}>🧵</button>
            <button className={`inv-pill ${typeFilter==='tool' ? 'inv-pill--active' : ''}`} onClick={() => setTypeFilter('tool')}>🪡</button>
            <button className="inv-add-btn inv-add-btn--secondary" onClick={() => openAdd('tool')}>
              <Plus size={15} /> {t('addToolToInventory')}
            </button>
            <button className="inv-add-btn" onClick={() => openAdd('yarn')}>
              <Plus size={15} /> {t('addYarnToInventory')}
            </button>
          </div>
        </div>
      </div>

      {/* ── Content ── */}
      {loading ? (
        <div className="inv-loading"><div className="spinner" style={{ width: 32, height: 32 }} /></div>
      ) : items.length === 0 ? (
        <div className="inv-empty">
          <Package size={48} strokeWidth={1.2} />
          <p>{t('inventoryEmpty')}</p>
          <p className="inv-empty-hint">{t('inventoryEmptyHint')}</p>
          <button className="inv-add-btn" onClick={() => openAdd('yarn')}>
            <Plus size={16} /> {t('addYarnToInventory')}
          </button>
        </div>
      ) : (
        <div className="inv-content">
          {(typeFilter === '' || typeFilter === 'yarn') && yarnItems.length > 0 && (
            <section className="inv-section">
              <h3 className="inv-section-title">🧵 {t('addYarnToInventory')} ({yarnItems.length})</h3>
              <div className="inv-grid">
                {yarnItems.map(item => (
                  <InventoryCard
                    key={item.id} item={item} t={t} language={language}
                    onAdjust={handleAdjust}
                    onEdit={item => { setEditItem(item); setModalInitialType(item.type); setModalOpen(true); }}
                    onDelete={id => setConfirmDelete(id)}
                  />
                ))}
              </div>
            </section>
          )}
          {(typeFilter === '' || typeFilter === 'tool') && toolItems.length > 0 && (
            <section className="inv-section">
              <h3 className="inv-section-title">🪡 {t('addToolToInventory')} ({toolItems.length})</h3>
              <div className="inv-grid">
                {toolItems.map(item => (
                  <InventoryCard
                    key={item.id} item={item} t={t} language={language}
                    onAdjust={handleAdjust}
                    onEdit={item => { setEditItem(item); setModalInitialType(item.type); setModalOpen(true); }}
                    onDelete={id => setConfirmDelete(id)}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Add/Edit modal */}
      {modalOpen && (
        <InventoryModal
          editItem={editItem}
          initialType={modalInitialType}
          onClose={() => { setModalOpen(false); setEditItem(null); }}
          onSaved={handleSaved}
          t={t}
          language={language}
        />
      )}

      {/* Delete confirm */}
      {confirmDelete && (
        <div className="modal-overlay" onClick={() => setConfirmDelete(null)}>
          <div className="inv-confirm-modal">
            <p>{t('deleteYarnConfirm')}</p>
            <div className="inv-confirm-btns">
              <button className="inv-confirm-yes" onClick={() => handleDelete(confirmDelete)}>{t('clearSessionsYes')}</button>
              <button className="inv-confirm-no" onClick={() => setConfirmDelete(null)}>{t('clearSessionsNo')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
