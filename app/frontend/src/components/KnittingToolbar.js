/**
 * KnittingToolbar.js  — Row counter + Notes panel
 * Two tabs only: Row (with save points) and Notes.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Wrench, X, Plus, Minus, Lock, Unlock,
  Trash2, StickyNote, Bookmark, Pencil, ChevronDown, ChevronUp,
} from 'lucide-react';
import './KnittingToolbar.css';

/* ─── localStorage ──────────────────────────────────────────────────────── */
const storageKey = (id) => `knitting-toolbar-${id}`;
function defaultState() {
  return { row: 0, rowLocked: false, saves: [], notes: [] };
}
function loadState(recipeId) {
  // Merge with defaultState so any fields added in newer versions
  // (like 'saves') are never undefined — avoids .length crashes.
  try {
    const r = localStorage.getItem(storageKey(recipeId));
    if (r) return { ...defaultState(), ...JSON.parse(r) };
  } catch (_) {}
  return defaultState();
}
function persistState(recipeId, state) {
  try { localStorage.setItem(storageKey(recipeId), JSON.stringify(state)); } catch (_) {}
}
const clamp0 = (v) => Math.max(0, v);

/* ═══════════════════════════════════════════════════════════
   SaveModal
═══════════════════════════════════════════════════════════ */
/* ─── Saved-category suggestions store ──────────────────────────────────────
   We keep a running list of every category the user has ever typed in
   localStorage so they get autocomplete suggestions on future saves.
   This is completely separate from the recipe categories on the backend.
────────────────────────────────────────────────────────────────────────── */
const CATS_STORE_KEY = 'knitting-toolbar-categories';
function loadSavedCats() {
  try { const r = localStorage.getItem(CATS_STORE_KEY); if (r) return JSON.parse(r); } catch (_) {}
  return [];
}
function addSavedCat(cat) {
  if (!cat) return;
  const existing = loadSavedCats();
  if (!existing.includes(cat)) {
    try { localStorage.setItem(CATS_STORE_KEY, JSON.stringify([...existing, cat])); } catch (_) {}
  }
}

/* ─── PillInput ─────────────────────────────────────────────────────────────
   Inline pill-tag input: type and press Space / Enter / comma to confirm.
   Shows a dropdown of suggestions from previously used values.
────────────────────────────────────────────────────────────────────────── */
function PillInput({ values, allOptions, onChange, placeholder }) {
  const [input, setInput] = React.useState('');
  const filtered = allOptions.filter(
    o => o.toLowerCase().includes(input.toLowerCase()) && !values.includes(o)
  );
  const add = (val) => {
    const v = val.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setInput('');
  };
  const remove = (v) => onChange(values.filter(x => x !== v));

  return (
    <div style={{ position: 'relative' }}>
      <div className="kt-pill-wrap" onClick={e => e.currentTarget.querySelector('input')?.focus()}>
        {values.map(v => (
          <span key={v} className="kt-pill-token">
            {v}
            <button type="button" className="kt-pill-token-x" onClick={() => remove(v)}>×</button>
          </span>
        ))}
        <input
          type="text"
          className="kt-pill-bare-input"
          placeholder={values.length === 0 ? placeholder : ''}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if ((e.key === ' ' || e.key === 'Enter' || e.key === ',') && input.trim()) {
              e.preventDefault();
              add(input);
            }
            if (e.key === 'Backspace' && !input && values.length) remove(values[values.length - 1]);
          }}
        />
      </div>
      {input && filtered.length > 0 && (
        <ul className="kt-pill-suggestions">
          {filtered.map(s => <li key={s} onMouseDown={() => add(s)}>{s}</li>)}
        </ul>
      )}
    </div>
  );
}

function SaveModal({ currentRow, existingSave, onConfirm, onClose, t }) {
  const [name,     setName]     = useState(existingSave?.name     ?? '');
  const [category, setCategory] = useState(existingSave?.category ?? '');
  const [note,     setNote]     = useState(existingSave?.note     ?? '');
  const [allCats,  setAllCats]  = useState(loadSavedCats);

  return (
    <div className="kt-modal-overlay" onClick={onClose}>
      <div className="kt-modal" onClick={e => e.stopPropagation()}>
        <div className="kt-modal-header">
          <span className="kt-modal-title">
            {existingSave ? (t('toolSaveEdit') || 'Edit save') : (t('toolSaveNew') || 'Save row')}
          </span>
          <button className="kt-close" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="kt-modal-row-badge">
          {t('toolRow') || 'Row'} {existingSave?.row ?? currentRow}
        </div>

        <div className="kt-modal-body">
          <label className="kt-modal-label">{t('toolSaveName') || 'Name'} *</label>
          <input
            className="kt-modal-input"
            placeholder={t('toolSaveNamePlaceholder') || 'e.g. Start of sleeve decrease'}
            value={name}
            onChange={e => setName(e.target.value)}
            autoFocus
          />

          <label className="kt-modal-label">{t('toolSaveCategory') || 'Category'}</label>
          <PillInput
            values={category ? [category] : []}
            allOptions={allCats}
            onChange={vals => setCategory(vals[vals.length - 1] ?? '')}
            placeholder={t('toolSaveCategoryPlaceholder') || 'Type a category, press Space…'}
          />

          <label className="kt-modal-label">{t('toolSaveNote') || 'Note'}</label>
          <textarea
            className="kt-modal-input kt-modal-textarea"
            placeholder={t('toolSaveNotePlaceholder') || 'Optional notes for this save…'}
            value={note}
            onChange={e => setNote(e.target.value)}
            rows={3}
          />
        </div>

        <div className="kt-modal-footer">
          <button className="kt-btn kt-btn--ghost kt-btn--sm" onClick={onClose}>
            {t('cancel') || 'Cancel'}
          </button>
          <button className="kt-btn kt-btn--accent" onClick={() => { if (name.trim()) onConfirm({ name: name.trim(), category, note: note.trim() }); }} disabled={!name.trim()}>
            {t('toolSaveConfirm') || 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   SaveCard
═══════════════════════════════════════════════════════════ */
function SaveCard({ save, onEdit, onDelete, t }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="kt-save-card">
      <button className="kt-save-card-main" onClick={() => setExpanded(e => !e)}>
        <div className="kt-save-card-left">
          <span className="kt-save-card-name">{save.name}</span>
          {save.category && <span className="kt-save-card-cat">{save.category}</span>}
        </div>
        <div className="kt-save-card-right">
          <span className="kt-save-card-row">{t('toolRow') || 'Row'} <strong>{save.row}</strong></span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>
      {expanded && (
        <div className="kt-save-card-detail">
          {save.note
            ? <p className="kt-save-card-note">{save.note}</p>
            : <p className="kt-save-card-note kt-save-card-note--empty">{t('toolSaveNoNote') || 'No note'}</p>
          }
          <div className="kt-save-card-actions">
            <span className="kt-save-card-ts">
              {new Date(save.ts).toLocaleString(
                t('language') === 'no' ? 'nb-NO' : 'en-US',
                { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
              )}
            </span>
            <div className="kt-save-card-btns">
              <button className="kt-icon-btn" onClick={() => onEdit(save)} title="Edit"><Pencil size={13} /></button>
              <button className="kt-icon-btn kt-icon-btn--danger" onClick={() => onDelete(save.id)} title="Delete"><Trash2 size={13} /></button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   Main component
═══════════════════════════════════════════════════════════ */
export default function KnittingToolbar({ recipeId, t }) {
  const [open,  setOpen]  = useState(false);
  const [tab,   setTab]   = useState('row');
  const [state, setState] = useState(() => loadState(recipeId) ?? defaultState());
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [editingSave,   setEditingSave]   = useState(null);
  const [noteText,  setNoteText]  = useState('');
  const [attachRow, setAttachRow] = useState(false);

  useEffect(() => { persistState(recipeId, state); }, [recipeId, state]);
  useEffect(() => { setState(loadState(recipeId) ?? defaultState()); }, [recipeId]);

  const update = useCallback((patch) => setState(prev => ({ ...prev, ...patch })), []);

  const rowUp    = () => { if (!state.rowLocked) update({ row: state.row + 1 }); };
  const rowDown  = () => { if (!state.rowLocked) update({ row: clamp0(state.row - 1) }); };
  const rowReset = () => { if (!state.rowLocked) update({ row: 0 }); };

  const handleSaveConfirm = ({ name, category, note }) => {
    if (editingSave) {
      update({ saves: state.saves.map(s => s.id === editingSave.id ? { ...s, name, category, note } : s) });
    } else {
      update({ saves: [{ id: Date.now(), name, category, note, row: state.row, ts: new Date().toISOString() }, ...state.saves] });
    }
    setSaveModalOpen(false);
    setEditingSave(null);
  };

  const addNote = () => {
    const text = noteText.trim();
    if (!text) return;
    update({ notes: [{ id: Date.now(), text, row: attachRow ? state.row : null, ts: new Date().toISOString() }, ...state.notes] });
    setNoteText('');
  };

  return (
    <>
      <button
        className={`kt-fab ${open ? 'kt-fab--active' : ''}`}
        onClick={() => setOpen(o => !o)}
        aria-label="Toggle knitting tools"
      >
        {open ? <X size={22} /> : <Wrench size={22} />}
      </button>

      {open && <div className="kt-backdrop" onClick={() => setOpen(false)} aria-hidden="true" />}

      <div className={`kt-panel ${open ? 'kt-panel--open' : ''}`} role="dialog">
        <div className="kt-panel-header">
          <span className="kt-panel-title"><Wrench size={16} />{t('toolbarTitle') || 'Knitting Tools'}</span>
          <button className="kt-close" onClick={() => setOpen(false)}><X size={18} /></button>
        </div>

        <div className="kt-tabs" role="tablist">
          <TabBtn id="row"   label={t('toolRow')   || 'Row'}   icon={<Minus size={14}/>}      active={tab} setTab={setTab} />
          <TabBtn id="notes" label={t('toolNotes') || 'Notes'} icon={<StickyNote size={14}/>} active={tab} setTab={setTab}
            badge={state.notes.length > 0 ? state.notes.length : null} />
        </div>

        <div className="kt-body">

          {/* ── ROW ── */}
          {tab === 'row' && (
            <div className="kt-tool">
              <div className="kt-counter-display">
                <span className="kt-counter-label">{t('toolRowLabel') || 'Current Row'}</span>
                <span className="kt-counter-number">{state.row}</span>
              </div>

              <div className="kt-counter-btns">
                <button className="kt-btn kt-btn--lg kt-btn--down" onClick={rowDown}
                  disabled={state.rowLocked || state.row === 0}><Minus size={26} /></button>
                <button className="kt-btn kt-btn--lg kt-btn--up" onClick={rowUp}
                  disabled={state.rowLocked}><Plus size={26} /></button>
              </div>

              <div className="kt-counter-actions">
                <button
                  className={`kt-btn kt-btn--sm ${state.rowLocked ? 'kt-btn--locked' : 'kt-btn--ghost'}`}
                  onClick={() => update({ rowLocked: !state.rowLocked })}
                >
                  {state.rowLocked ? <Lock size={14} /> : <Unlock size={14} />}
                  <span>{state.rowLocked ? (t('unlock') || 'Unlock') : (t('lock') || 'Lock')}</span>
                </button>
                <button className="kt-btn kt-btn--sm kt-btn--ghost" onClick={rowReset} disabled={state.rowLocked}>
                  <Trash2 size={14} /><span>{t('reset') || 'Reset'}</span>
                </button>
                <button className="kt-btn kt-btn--sm kt-btn--save"
                  onClick={() => { setEditingSave(null); setSaveModalOpen(true); }}>
                  <Bookmark size={14} /><span>{t('toolSaveBtn') || 'Save'}</span>
                </button>
              </div>

              {state.rowLocked && (
                <p className="kt-locked-notice">🔒 {t('rowLockedNotice') || 'Row counter is locked — tap Unlock to edit'}</p>
              )}

              {state.saves.length > 0 && (
                <div className="kt-saves-section">
                  <span className="kt-saves-heading">
                    {t('toolSavedRows') || 'Saved rows'}
                    <span className="kt-saves-count">{state.saves.length}</span>
                  </span>
                  <div className="kt-saves-list">
                    {state.saves.map(save => (
                      <SaveCard key={save.id} save={save}
                        onEdit={s => { setEditingSave(s); setSaveModalOpen(true); }}
                        onDelete={id => update({ saves: state.saves.filter(s => s.id !== id) })}
                        t={t} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── NOTES ── */}
          {tab === 'notes' && (
            <div className="kt-tool kt-tool--notes">
              <div className="kt-note-compose">
                <textarea className="kt-note-input"
                  placeholder={t('toolNotesPlaceholder') || 'Write a quick note…'}
                  value={noteText} onChange={e => setNoteText(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); addNote(); } }}
                  rows={3} />
                <div className="kt-note-compose-footer">
                  <label className="kt-attach-label">
                    <input type="checkbox" checked={attachRow} onChange={e => setAttachRow(e.target.checked)} />
                    <span>{t('toolNotesAttachRow') || 'Attach to row'}{attachRow ? ` ${state.row}` : ''}</span>
                  </label>
                  <button className="kt-btn kt-btn--accent" onClick={addNote} disabled={!noteText.trim()}>
                    {t('toolNotesSave') || 'Add Note'}
                  </button>
                </div>
              </div>
              <div className="kt-notes-list">
                {state.notes.length === 0 ? (
                  <p className="kt-notes-empty">
                    <StickyNote size={28} style={{ opacity: 0.3 }} />
                    <span>{t('toolNotesEmpty') || 'No notes yet'}</span>
                  </p>
                ) : (
                  state.notes.map(note => (
                    <div key={note.id} className="kt-note-card">
                      {note.row !== null && <span className="kt-note-row-badge">{t('toolRow') || 'Row'} {note.row}</span>}
                      <p className="kt-note-text">{note.text}</p>
                      <div className="kt-note-meta">
                        <span className="kt-note-ts">
                          {new Date(note.ts).toLocaleString(
                            t('language') === 'no' ? 'nb-NO' : 'en-US',
                            { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
                          )}
                        </span>
                        <button className="kt-note-delete" onClick={() => update({ notes: state.notes.filter(n => n.id !== note.id) })}>
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

        </div>
      </div>

      {saveModalOpen && (
        <SaveModal
          currentRow={state.row}
          existingSave={editingSave}
          onConfirm={handleSaveConfirm}
          onClose={() => { setSaveModalOpen(false); setEditingSave(null); }}
          t={t}
        />
      )}
    </>
  );
}

function TabBtn({ id, label, icon, active, setTab, badge }) {
  return (
    <button role="tab" aria-selected={active === id}
      className={`kt-tab ${active === id ? 'kt-tab--active' : ''}`}
      onClick={() => setTab(id)}>
      {icon}<span>{label}</span>
      {badge != null && <span className="kt-tab-badge">{badge}</span>}
    </button>
  );
}
