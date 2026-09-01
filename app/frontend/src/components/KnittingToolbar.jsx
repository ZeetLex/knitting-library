import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bookmark, Calculator, ChevronDown, ChevronUp, Minus, Pencil, Plus, RotateCcw,
  Save, StickyNote, Trash2, Wrench, X,
} from 'lucide-react';
import {
  fetchKnittingTools, saveKnittingTools, fetchUserKnittingTools, saveUserKnittingTools,
} from '../utils/api';
import './KnittingToolbar.css';

const clamp0 = value => Math.max(0, Number.isFinite(Number(value)) ? Number(value) : 0);

const MAX_COUNTERS = 100;
const MAX_COUNTER_LABEL = 120;

const newId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;

function defaultState() {
  return {
    currentRow: 0,
    completedRounds: 0,
    saves: [],
    noteSheet: '',
    calculator: { current: 80, target: 100 },
    counterMode: 'rounds',
    counters: [],
  };
}

function normalizeState(raw) {
  const base = defaultState();
  if (!raw || typeof raw !== 'object') return base;
  return {
    ...base,
    ...raw,
    currentRow: clamp0(raw.currentRow ?? raw.row ?? 0),
    completedRounds: clamp0(raw.completedRounds ?? 0),
    saves: Array.isArray(raw.saves) ? raw.saves : [],
    noteSheet: typeof raw.noteSheet === 'string' ? raw.noteSheet : '',
    calculator: {
      ...base.calculator,
      ...(raw.calculator && typeof raw.calculator === 'object' ? raw.calculator : {}),
    },
    counterMode: raw.counterMode === 'counters' ? 'counters' : 'rounds',
    counters: Array.isArray(raw.counters)
      ? raw.counters
          .filter(item => item && typeof item === 'object')
          .slice(0, MAX_COUNTERS)
          .map((item, index) => ({
            id: String(item.id || `legacy-${index}`),
            label: typeof item.label === 'string' ? item.label.slice(0, MAX_COUNTER_LABEL) : '',
            value: clamp0(item.value),
            createdAt: typeof item.createdAt === 'string' ? item.createdAt : '',
          }))
      : [],
  };
}

function buildEvenInstructions(current, target, t) {
  const start = Math.max(0, Math.floor(Number(current) || 0));
  const end = Math.max(0, Math.floor(Number(target) || 0));
  const diff = Math.abs(end - start);
  const action = end > start ? 'increase' : end < start ? 'decrease' : 'same';
  if (!start || !end) return { action, summary: t('toolCalcEnterValues') || 'Enter stitch counts to calculate.' };
  if (action === 'same') return { action, summary: t('toolCalcNoChange') || 'No increases or decreases needed.' };

  const base = Math.floor(start / diff);
  const extra = start % diff;
  const intervals = Array.from({ length: diff }, (_, index) => base + (index < extra ? 1 : 0));
  const grouped = intervals.reduce((acc, interval) => {
    acc[interval] = (acc[interval] || 0) + 1;
    return acc;
  }, {});
  const parts = Object.entries(grouped)
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .map(([interval, count]) => {
      const key = action === 'increase' ? 'toolCalcIncreasePart' : 'toolCalcDecreasePart';
      return (t(key) || '{count} times: work {interval} stitches, then change 1 stitch')
        .replace('{count}', count)
        .replace('{interval}', interval);
    });
  const summaryKey = action === 'increase' ? 'toolCalcIncreaseSummary' : 'toolCalcDecreaseSummary';
  return {
    action,
    summary: (t(summaryKey) || '{diff} changes from {current} to {target} stitches.')
      .replace('{diff}', diff)
      .replace('{current}', start)
      .replace('{target}', end),
    parts,
  };
}

function SaveModal({ currentCount, existingSave, onConfirm, onClose, t }) {
  const [name, setName] = useState(existingSave?.name || '');
  const [category, setCategory] = useState(existingSave?.category || '');
  const [note, setNote] = useState(existingSave?.note || '');

  return (
    <div className="kt-modal-overlay" onClick={onClose}>
      <div className="kt-modal" onClick={event => event.stopPropagation()}>
        <div className="kt-modal-header">
          <span className="kt-modal-title">{existingSave ? t('toolSaveEdit') : t('toolSaveNew')}</span>
          <button className="kt-close" onClick={onClose} aria-label={t('cancel')}><X size={18} /></button>
        </div>
        <div className="kt-modal-count-badge">{t('toolCompletedRounds') || 'Completed rounds'} {existingSave?.count ?? currentCount}</div>
        <div className="kt-modal-body">
          <label className="kt-modal-label">{t('toolSaveName')} *</label>
          <input className="kt-modal-input" value={name} onChange={event => setName(event.target.value)} placeholder={t('toolSaveNamePlaceholder')} autoFocus />
          <label className="kt-modal-label">{t('toolSaveCategory')}</label>
          <input className="kt-modal-input" value={category} onChange={event => setCategory(event.target.value)} placeholder={t('toolSaveCategoryPlaceholder')} />
          <label className="kt-modal-label">{t('toolSaveNote')}</label>
          <textarea className="kt-modal-input kt-modal-textarea" value={note} onChange={event => setNote(event.target.value)} placeholder={t('toolSaveNotePlaceholder')} rows={3} />
        </div>
        <div className="kt-modal-footer">
          <button className="kt-btn kt-btn--ghost" onClick={onClose}>{t('cancel')}</button>
          <button
            className="kt-btn kt-btn--accent"
            disabled={!name.trim()}
            onClick={() => onConfirm({ name: name.trim(), category: category.trim(), note: note.trim() })}
          >
            {t('toolSaveConfirm')}
          </button>
        </div>
      </div>
    </div>
  );
}

function SaveCard({ save, onEdit, onDelete, t }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="kt-save-card">
      <button className="kt-save-card-main" onClick={() => setOpen(value => !value)}>
        <span className="kt-save-count">{save.count}</span>
        <span className="kt-save-copy">
          <strong>{save.name}</strong>
          {save.category && <small>{save.category}</small>}
        </span>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      {open && (
        <div className="kt-save-card-detail">
          <dl>
            <div><dt>{t('toolSaveName')}</dt><dd>{save.name}</dd></div>
            <div><dt>{t('toolSaveCategory')}</dt><dd>{save.category || '-'}</dd></div>
            <div><dt>{t('toolSaveNote')}</dt><dd>{save.note || t('toolSaveNoNote')}</dd></div>
          </dl>
          <div className="kt-save-card-actions">
            <button className="kt-icon-btn" onClick={() => onEdit(save)} aria-label={t('edit')}><Pencil size={14} /></button>
            <button className="kt-icon-btn kt-icon-btn--danger" onClick={() => onDelete(save.id)} aria-label={t('delete')}><Trash2 size={14} /></button>
          </div>
        </div>
      )}
    </div>
  );
}

function CounterRow({ counter, onIncrement, onDecrement, onOpen, t }) {
  const label = counter.label || t('toolCounterUntitled');
  return (
    <div className="kt-counter-row">
      <button
        className="kt-counter-row-step"
        onClick={() => onDecrement(counter.id)}
        disabled={counter.value === 0}
        aria-label={t('decrease')}
      >
        <Minus size={22} />
      </button>
      <button className="kt-counter-row-main" onClick={() => onOpen(counter)} aria-label={`${label} — ${t('edit')}`}>
        <span className="kt-counter-row-value">{counter.value}</span>
        <span className="kt-counter-row-label">{label}</span>
      </button>
      <button className="kt-counter-row-step" onClick={() => onIncrement(counter.id)} aria-label={t('increase')}>
        <Plus size={22} />
      </button>
    </div>
  );
}

function CounterModal({ counter, onSave, onReset, onDelete, onClose, t }) {
  const [label, setLabel] = useState(counter?.label || '');

  return (
    <div className="kt-modal-overlay" onClick={onClose}>
      <div className="kt-modal" onClick={event => event.stopPropagation()}>
        <div className="kt-modal-header">
          <span className="kt-modal-title">{counter ? t('toolCounterEditTitle') : t('toolCounterCreateTitle')}</span>
          <button className="kt-close" onClick={onClose} aria-label={t('cancel')}><X size={18} /></button>
        </div>
        {counter && <div className="kt-modal-count-badge">{counter.value}</div>}
        <div className="kt-modal-body">
          <label className="kt-modal-label">{t('toolCounterNameLabel')} *</label>
          <input
            className="kt-modal-input"
            value={label}
            onChange={event => setLabel(event.target.value.slice(0, MAX_COUNTER_LABEL))}
            placeholder={t('toolCounterNamePlaceholder')}
            autoFocus
          />
          {counter && (
            <div className="kt-modal-row-actions">
              <button
                className="kt-btn kt-btn--ghost"
                onClick={() => {
                  if (!window.confirm((t('toolCounterResetConfirm') || 'Reset {name}?').replace('{name}', counter.label || t('toolCounterUntitled')))) return;
                  onReset(counter.id);
                  onClose();
                }}
              >
                <RotateCcw size={15} />{t('reset')}
              </button>
              <button
                className="kt-btn kt-btn--danger"
                onClick={() => {
                  if (!window.confirm((t('toolCounterDeleteConfirm') || 'Delete {name}?').replace('{name}', counter.label || t('toolCounterUntitled')))) return;
                  onDelete(counter.id);
                  onClose();
                }}
              >
                <Trash2 size={15} />{t('delete')}
              </button>
            </div>
          )}
        </div>
        <div className="kt-modal-footer">
          <button className="kt-btn kt-btn--ghost" onClick={onClose}>{t('cancel')}</button>
          <button
            className="kt-btn kt-btn--accent"
            disabled={!label.trim()}
            onClick={() => onSave(label.trim())}
          >
            {t('toolSaveConfirm')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function KnittingToolbar({ scope = 'recipe', recipeId = null, t, open = false, onClose }) {
  const [tab, setTab] = useState('counter');
  const [state, setState] = useState(defaultState);
  const [loading, setLoading] = useState(false);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [editingSave, setEditingSave] = useState(null);
  const [error, setError] = useState('');
  const [counterModalOpen, setCounterModalOpen] = useState(false);
  const [editingCounter, setEditingCounter] = useState(null);
  const [activated, setActivated] = useState(open);
  const saveTimerRef = useRef(null);
  const loadedRef = useRef(false);
  const stateRef = useRef(state);
  const longPressRef = useRef(null);
  const longPressTriggeredRef = useRef(false);
  const tRef = useRef(t);

  const isGlobal = scope === 'global';
  const scopeKey = isGlobal ? 'global' : `recipe:${recipeId || ''}`;

  // `t` is a fresh closure on every AppContext render, so it must never appear in
  // the load/save effect deps — reading it through a ref keeps those deps primitive.
  useEffect(() => {
    tRef.current = t;
  });

  const io = useMemo(() => {
    if (isGlobal) {
      return {
        load: () => fetchUserKnittingTools(),
        save: (data, options) => saveUserKnittingTools(data, options),
      };
    }
    if (!recipeId) {
      return { load: () => Promise.resolve({ data: {} }), save: () => Promise.resolve({}) };
    }
    return {
      load: () => fetchKnittingTools(recipeId),
      save: (data, options) => saveKnittingTools(recipeId, data, options),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeKey]);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    if (open) setActivated(true);
  }, [open]);

  useEffect(() => {
    loadedRef.current = false;
    setState(defaultState());
    if (!activated) return undefined;
    let cancelled = false;
    setLoading(true);
    setError('');
    io.load()
      .then(result => {
        if (!cancelled) {
          setState(normalizeState(result?.data));
          loadedRef.current = true;
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(tRef.current('toolLoadError') || 'Could not load tools.');
          loadedRef.current = true;
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
      if (loadedRef.current) io.save(stateRef.current, { keepalive: true }).catch(() => {});
    };
  }, [io, activated]);

  useEffect(() => {
    if (!loadedRef.current) return undefined;
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(() => {
      io.save(state).catch(() => setError(tRef.current('toolSaveError') || 'Could not save tools.'));
    }, 450);
    return () => {
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    };
  }, [io, state]);

  const update = useCallback(patch => {
    setState(previous => ({ ...previous, ...patch }));
  }, []);

  const incrementCompleted = () => update({ completedRounds: state.completedRounds + 1, currentRow: 0 });
  const decrementCompleted = () => update({ completedRounds: clamp0(state.completedRounds - 1) });

  const beginCenterPress = () => {
    longPressTriggeredRef.current = false;
    if (longPressRef.current) window.clearTimeout(longPressRef.current);
    longPressRef.current = window.setTimeout(() => {
      longPressTriggeredRef.current = true;
      decrementCompleted();
    }, 600);
  };

  const endCenterPress = () => {
    if (longPressRef.current) window.clearTimeout(longPressRef.current);
    if (!longPressTriggeredRef.current) incrementCompleted();
    longPressRef.current = null;
  };

  const handleSaveConfirm = ({ name, category, note }) => {
    if (editingSave) {
      update({ saves: state.saves.map(save => save.id === editingSave.id ? { ...save, name, category, note } : save) });
    } else {
      update({
        saves: [{
          id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
          name,
          category,
          note,
          count: state.completedRounds,
          row: state.currentRow,
          ts: new Date().toISOString(),
        }, ...state.saves],
      });
    }
    setEditingSave(null);
    setSaveModalOpen(false);
  };

  const resetCounter = () => {
    if (!window.confirm(t('toolResetConfirm') || 'Reset the counter?')) return;
    update({ currentRow: 0, completedRounds: 0 });
  };

  const bumpCounter = (id, delta) => update({
    counters: state.counters.map(counter =>
      counter.id === id ? { ...counter, value: clamp0(counter.value + delta) } : counter),
  });

  const handleCounterSave = label => {
    if (editingCounter) {
      update({
        counters: state.counters.map(counter =>
          counter.id === editingCounter.id ? { ...counter, label } : counter),
      });
    } else {
      update({
        counters: [...state.counters, { id: newId(), label, value: 0, createdAt: new Date().toISOString() }],
      });
    }
    setEditingCounter(null);
    setCounterModalOpen(false);
  };

  const openNewCounter = () => {
    if (state.counters.length >= MAX_COUNTERS) {
      setError(t('toolCounterLimitReached') || 'Counter limit reached.');
      return;
    }
    setError('');
    setEditingCounter(null);
    setCounterModalOpen(true);
  };

  const deleteCounter = id => {
    setError('');
    update({ counters: state.counters.filter(counter => counter.id !== id) });
  };

  const handleClose = () => {
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    if (loadedRef.current) io.save(stateRef.current, { keepalive: true }).catch(() => {});
    onClose?.();
  };

  const calc = useMemo(
    () => buildEvenInstructions(state.calculator.current, state.calculator.target, t),
    [state.calculator.current, state.calculator.target, t]
  );

  const panelTitle = isGlobal ? t('toolbarTitleGlobal') : t('toolbarTitle');

  return (
    <>
      <aside
        className={`kt-panel ${open ? 'kt-panel--open' : ''} ${isGlobal ? 'kt-panel--global' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={panelTitle}
      >
        <div className="kt-panel-header">
          <span className="kt-panel-title"><Wrench size={16} />{panelTitle}</span>
          <button className="kt-close" onClick={handleClose} aria-label={t('cancel')}><X size={18} /></button>
        </div>

        <div className="kt-tabs" role="tablist">
          <TabBtn id="counter" label={t('toolCounter') || t('toolRow')} icon={<Minus size={15} />} active={tab} setTab={setTab} />
          <TabBtn id="shape" label={t('toolShape') || 'Increase/decrease'} icon={<Calculator size={15} />} active={tab} setTab={setTab} />
          <TabBtn id="notes" label={t('toolNotes')} icon={<StickyNote size={15} />} active={tab} setTab={setTab} />
        </div>

        <div className="kt-body">
          {loading && <div className="kt-loading">{t('loading')}</div>}
          {error && <p className="kt-error">{error}</p>}

          {!loading && tab === 'counter' && (
            <div className="kt-tool kt-tool--counter">
              <div className="kt-submodes" role="tablist">
                <button
                  role="tab"
                  aria-selected={state.counterMode !== 'counters'}
                  className={`kt-submode ${state.counterMode !== 'counters' ? 'kt-submode--active' : ''}`}
                  onClick={() => update({ counterMode: 'rounds' })}
                >
                  {t('toolCounterModeRounds')}
                </button>
                <button
                  role="tab"
                  aria-selected={state.counterMode === 'counters'}
                  className={`kt-submode ${state.counterMode === 'counters' ? 'kt-submode--active' : ''}`}
                  onClick={() => update({ counterMode: 'counters' })}
                >
                  {t('toolCounterModeCounters')}
                </button>
              </div>

              {state.counterMode === 'counters' ? (
                <div className="kt-counters">
                  {state.counters.length === 0 ? (
                    <div className="kt-counters-empty">
                      <strong>{t('toolCountersEmptyTitle')}</strong>
                      <p>{t('toolCountersEmptyHint')}</p>
                    </div>
                  ) : (
                    state.counters.map(counter => (
                      <CounterRow
                        key={counter.id}
                        counter={counter}
                        t={t}
                        onIncrement={id => bumpCounter(id, 1)}
                        onDecrement={id => bumpCounter(id, -1)}
                        onOpen={item => { setEditingCounter(item); setCounterModalOpen(true); }}
                      />
                    ))
                  )}
                  <button className="kt-counter-add" onClick={openNewCounter}>
                    {t('toolCounterNew')}<Plus size={20} />
                  </button>
                </div>
              ) : (
                <>
                <div className="kt-counter-stage">
                  <button className="kt-counter-side" onClick={() => update({ currentRow: clamp0(state.currentRow - 1) })} disabled={state.currentRow === 0} aria-label={t('decrease') || 'Decrease'}>
                    <Minus size={34} />
                  </button>
                  <button
                    className="kt-counter-center"
                    onPointerDown={beginCenterPress}
                    onPointerUp={endCenterPress}
                    onContextMenu={event => event.preventDefault()}
                    onPointerLeave={() => {
                      if (longPressRef.current) window.clearTimeout(longPressRef.current);
                      longPressRef.current = null;
                    }}
                  >
                    <span className="kt-counter-number">{state.currentRow}</span>
                    <span className="kt-counter-help">{t('toolCounterTapHint')}</span>
                  </button>
                  <button className="kt-counter-side" onClick={() => update({ currentRow: state.currentRow + 1 })} aria-label={t('increase') || 'Increase'}>
                    <Plus size={36} />
                  </button>
                </div>

                <div className="kt-counter-bottom">
                  <div className="kt-completed-box">
                    <span>{state.completedRounds}</span>
                    <small>{t('toolCompletedRounds')}</small>
                  </div>
                  <button className="kt-btn kt-btn--save" onClick={() => { setEditingSave(null); setSaveModalOpen(true); }}>
                    <Bookmark size={15} />{t('toolSaveBtn')}
                  </button>
                  <button className="kt-btn kt-btn--ghost" onClick={resetCounter}>
                    <RotateCcw size={15} />{t('discard') || t('reset')}
                  </button>
                </div>

                <div className="kt-saves-section">
                  {state.saves.length === 0 ? (
                    <p className="kt-empty-line">{t('toolSavedRowsEmpty') || 'No saved counts yet.'}</p>
                  ) : (
                    state.saves.map(save => (
                      <SaveCard
                        key={save.id}
                        save={save}
                        t={t}
                        onEdit={item => { setEditingSave(item); setSaveModalOpen(true); }}
                        onDelete={id => update({ saves: state.saves.filter(save => save.id !== id) })}
                      />
                    ))
                  )}
                </div>
                </>
              )}
            </div>
          )}

          {!loading && tab === 'shape' && (
            <div className="kt-tool kt-tool--shape">
              <label className="kt-field">
                <span>{t('toolCalcCurrent')}</span>
                <input type="number" min="0" value={state.calculator.current} onChange={event => update({ calculator: { ...state.calculator, current: event.target.value } })} />
              </label>
              <label className="kt-field">
                <span>{t('toolCalcTarget')}</span>
                <input type="number" min="0" value={state.calculator.target} onChange={event => update({ calculator: { ...state.calculator, target: event.target.value } })} />
              </label>
              <div className={`kt-calc-result kt-calc-result--${calc.action}`}>
                <strong>{calc.summary}</strong>
                {calc.parts?.map(part => <p key={part}>{part}</p>)}
              </div>
              <p className="kt-calc-help">{t('toolCalcManualHelp')}</p>
            </div>
          )}

          {!loading && tab === 'notes' && (
            <div className="kt-tool kt-tool--notes">
              <textarea
                className="kt-note-sheet"
                value={state.noteSheet}
                onChange={event => update({ noteSheet: event.target.value })}
                placeholder={
                  isGlobal
                    ? (t('toolNotesSheetPlaceholderGlobal') || t('toolNotesPlaceholder'))
                    : (t('toolNotesSheetPlaceholder') || t('toolNotesPlaceholder'))
                }
              />
              <span className="kt-autosave"><Save size={13} />{t('toolAutosaves') || 'Auto-saves'}</span>
            </div>
          )}
        </div>
      </aside>

      {open && <button className="kt-screen-backdrop" onClick={handleClose} aria-label={t('cancel')} />}

      {saveModalOpen && (
        <SaveModal
          currentCount={state.completedRounds}
          existingSave={editingSave}
          onConfirm={handleSaveConfirm}
          onClose={() => { setSaveModalOpen(false); setEditingSave(null); }}
          t={t}
        />
      )}

      {counterModalOpen && (
        <CounterModal
          counter={editingCounter}
          onSave={handleCounterSave}
          onReset={id => update({
            counters: state.counters.map(counter =>
              counter.id === id ? { ...counter, value: 0 } : counter),
          })}
          onDelete={deleteCounter}
          onClose={() => { setCounterModalOpen(false); setEditingCounter(null); }}
          t={t}
        />
      )}
    </>
  );
}

function TabBtn({ id, label, icon, active, setTab }) {
  return (
    <button role="tab" aria-selected={active === id} className={`kt-tab ${active === id ? 'kt-tab--active' : ''}`} onClick={() => setTab(id)}>
      {icon}<span>{label}</span>
    </button>
  );
}
