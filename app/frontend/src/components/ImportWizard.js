import React, { useState, useEffect, useRef, useCallback, Component } from 'react';
import { createPortal } from 'react-dom';
import {
  X, FileText, Image, ChevronRight, SkipForward, StopCircle,
  CheckCircle, FolderOpen, RefreshCw, AlertCircle, Upload,
  FolderInput, ArrowLeft, AlertTriangle,
} from 'lucide-react';
import { useApp } from '../utils/AppContext';
import {
  uploadImportGroup, getImportQueue, confirmImportItem,
  discardImportItem, fetchCategories, fetchTags, thumbnailUrl,
  fetchPdfPages, pdfPageUrl, imageUrl, checkImportDuplicate,
} from '../utils/api';
import './ImportWizard.css';

// ── Error boundary ────────────────────────────────────────────────────────────
// MUST come after imports. Catches any JS crash inside the wizard and shows
// the error message instead of a white screen.
class WizardErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(e) { return { error: e }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: '32px', color: 'var(--text)', fontFamily: 'monospace' }}>
          <h3 style={{ color: 'red', marginBottom: 12 }}>Wizard crashed — error details:</h3>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, background: 'var(--bg-hover)', padding: 16, borderRadius: 8, overflowX: 'auto' }}>
            {this.state.error.message}{'\n\n'}{this.state.error.stack}
          </pre>
          <button style={{ marginTop: 16, padding: '8px 16px', cursor: 'pointer' }}
            onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.webp']);
const PDF_EXT    = '.pdf';
function extOf(name) { return name.slice(name.lastIndexOf('.')).toLowerCase(); }
function isSupported(name) { const e = extOf(name); return e === PDF_EXT || IMAGE_EXTS.has(e); }

/**
 * Group files from a webkitdirectory input into recipe candidates.
 * - Root-level PDF → its own group
 * - Sub-folder     → one group per sub-folder
 * - Root-level images → one group named after the root folder
 */
function groupFilesByFolder(fileList) {
  const groups    = new Map();
  const rootImages = [];
  const firstPath  = fileList[0]?.webkitRelativePath || '';
  const rootFolder = firstPath.split('/')[0] || 'Import';

  for (const file of fileList) {
    if (!isSupported(file.name)) continue;
    const parts = file.webkitRelativePath.split('/');
    if (parts.length === 2) {
      if (extOf(file.name) === PDF_EXT) {
        if (!groups.has(file.name)) groups.set(file.name, []);
        groups.get(file.name).push(file);
      } else {
        rootImages.push(file);
      }
    } else if (parts.length >= 3) {
      const sub = parts[1];
      if (!groups.has(sub)) groups.set(sub, []);
      groups.get(sub).push(file);
    }
  }
  if (rootImages.length) groups.set(rootFolder, rootImages);

  return Array.from(groups.entries()).map(([groupName, files]) => ({
    groupName,
    files: files.sort((a, b) => a.name.localeCompare(b.name)),
    type: files.some(f => extOf(f.name) === PDF_EXT) ? 'pdf' : 'images',
  }));
}

// ── PillInput ─────────────────────────────────────────────────────────────────
function PillInput({ label, values, allOptions, onChange, placeholder }) {
  const [input, setInput] = useState('');
  const filtered = allOptions.filter(
    o => o.toLowerCase().includes(input.toLowerCase()) && !values.includes(o)
  );
  const add = (val) => { const v = val.trim(); if (v && !values.includes(v)) onChange([...values, v]); setInput(''); };
  const remove = (v) => onChange(values.filter(x => x !== v));

  return (
    <div className="iw-pill-field">
      <label className="iw-label">{label}</label>
      <div className="iw-pill-wrap">
        {values.map(v => (
          <span key={v} className="iw-pill">{v}<button className="iw-pill-x" onClick={() => remove(v)}>×</button></span>
        ))}
        <input
          type="text"
          className="iw-pill-input"
          placeholder={values.length === 0 ? placeholder : ''}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if ((e.key === 'Enter' || e.key === ',') && input.trim()) { e.preventDefault(); add(input); }
            if (e.key === 'Backspace' && !input && values.length) remove(values[values.length - 1]);
          }}
        />
      </div>
      {input && filtered.length > 0 && (
        <ul className="iw-suggestions">
          {filtered.map(s => <li key={s} onMouseDown={() => add(s)}>{s}</li>)}
        </ul>
      )}
    </div>
  );
}

// ── ViewerPage — single page with spinner until loaded ────────────────────────
function ViewerPage({ src, alt }) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError]   = useState(false);
  const imgRef = useRef(null);

  useEffect(() => {
    setLoaded(false);
    setError(false);
    if (imgRef.current && imgRef.current.complete && imgRef.current.naturalWidth > 0) {
      setLoaded(true);
    }
  }, [src]);

  return (
    <div className="iw-page-wrap">
      {!loaded && !error && (
        <div className="iw-page-placeholder">
          <RefreshCw size={18} className="iw-spin" />
        </div>
      )}
      {error && (
        <div className="iw-page-placeholder iw-page-error">
          <AlertCircle size={18} />
        </div>
      )}
      <img
        ref={imgRef}
        src={src}
        alt={alt}
        className={`iw-viewer-page ${loaded ? 'loaded' : 'hidden'}`}
        onLoad={() => setLoaded(true)}
        onError={() => { setError(true); setLoaded(false); }}
      />
    </div>
  );
}

// ── Phase 1: Choose files ─────────────────────────────────────────────────────
function UploadPhase({ onGroupsReady, onClose, t }) {
  const folderInputRef = useRef(null);
  const fileInputRef   = useRef(null);
  const [dragOver, setDragOver]   = useState(false);
  const [groups, setGroups]       = useState(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress]   = useState({ done: 0, total: 0 });
  const [uploadError, setUploadError] = useState('');

  const processFileList = (fileList) => {
    if (!fileList || fileList.length === 0) return;
    setGroups(groupFilesByFolder(fileList));
  };

  const handleFolderSelect = (e) => processFileList(e.target.files);

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files).filter(f => isSupported(f.name));
    if (!files.length) return;
    const result = []; const imgs = [];
    for (const f of files) {
      if (extOf(f.name) === PDF_EXT) result.push({ groupName: f.name, files: [f], type: 'pdf' });
      else imgs.push(f);
    }
    if (imgs.length) result.push({ groupName: 'Selected images', files: imgs, type: 'images' });
    setGroups(result);
  };

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    const allFiles = Array.from(e.dataTransfer.files).filter(f => isSupported(f.name));
    if (!allFiles.length) return;
    const result = []; const imgs = [];
    for (const f of allFiles) {
      if (extOf(f.name) === PDF_EXT) result.push({ groupName: f.name, files: [f], type: 'pdf' });
      else imgs.push(f);
    }
    if (imgs.length) result.push({ groupName: 'Dropped images', files: imgs, type: 'images' });
    setGroups(result);
  };

  const startUpload = async () => {
    if (!groups || !groups.length) return;
    setUploading(true); setUploadError('');
    setProgress({ done: 0, total: groups.length });
    const staged = [];
    for (let i = 0; i < groups.length; i++) {
      const g = groups[i];
      try {
        const result = await uploadImportGroup(g.groupName, g.files);
        staged.push(result);
      } catch (e) { console.warn(`Skipping "${g.groupName}": ${e.message}`); }
      setProgress({ done: i + 1, total: groups.length });
    }
    setUploading(false);
    if (!staged.length) { setUploadError('No items could be uploaded. Check file formats.'); return; }
    onGroupsReady(staged);
  };

  return (
    <div className="iw-upload-phase">
      {!groups && (
        <div
          className={`iw-drop-zone ${dragOver ? 'drag-over' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <FolderInput size={52} className="iw-drop-icon" />
          <h3 className="iw-drop-title">{t('importDropTitle')}</h3>
          <p className="iw-drop-hint">{t('importDropHint')}</p>
          <div className="iw-drop-btns">
            <button className="iw-btn-primary" onClick={() => folderInputRef.current?.click()}>
              <FolderOpen size={16} /> {t('importSelectFolder')}
            </button>
            <button className="iw-btn-secondary" onClick={() => fileInputRef.current?.click()}>
              <Upload size={15} /> {t('importSelectFiles')}
            </button>
          </div>
          <p className="iw-drop-formats">PDF · JPG · PNG · WebP</p>
          <input ref={folderInputRef} type="file" style={{display:'none'}} webkitdirectory="true" directory="true" multiple onChange={handleFolderSelect} />
          <input ref={fileInputRef} type="file" style={{display:'none'}} multiple accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={handleFileSelect} />
        </div>
      )}

      {groups && !uploading && (
        <>
          <div className="iw-groups-preview">
            <div className="iw-groups-header">
              <button className="iw-btn-ghost iw-back-btn" onClick={() => setGroups(null)}>
                <ArrowLeft size={14} /> {t('back')}
              </button>
              <span className="iw-groups-count">
                {groups.length} {groups.length === 1 ? t('importRecipeDetected') : t('importRecipesDetected')}
              </span>
            </div>
            <div className="iw-groups-list">
              {groups.map((g, i) => (
                <div key={i} className="iw-group-row">
                  {g.type === 'pdf'
                    ? <FileText size={15} className="iw-group-icon pdf" />
                    : <Image    size={15} className="iw-group-icon img" />
                  }
                  <span className="iw-group-name">{g.groupName}</span>
                  <span className="iw-group-meta">
                    {g.type === 'pdf' ? 'PDF' : `${g.files.length} image${g.files.length !== 1 ? 's' : ''}`}
                  </span>
                </div>
              ))}
            </div>
            {uploadError && <p className="iw-upload-error">{uploadError}</p>}
          </div>
          <div className="iw-footer">
            <button className="iw-btn-ghost" onClick={onClose}><StopCircle size={15} /> {t('cancel')}</button>
            <button className="iw-btn-primary" onClick={startUpload}>
              {t('importStartWizard')} <ChevronRight size={15} />
            </button>
          </div>
        </>
      )}

      {uploading && (
        <div className="iw-uploading">
          <RefreshCw size={36} className="iw-spin" />
          <h3>{t('importUploading')}</h3>
          <p className="iw-upload-progress-label">{progress.done} / {progress.total}</p>
          <div className="iw-upload-track">
            <div className="iw-upload-fill" style={{width:`${(progress.done/progress.total)*100}%`}} />
          </div>
          <p className="iw-upload-hint">{t('importUploadingHint')}</p>
        </div>
      )}
    </div>
  );
}

// ── Phase 2: Wizard ───────────────────────────────────────────────────────────
function WizardPhase({ initialItems, onClose, onRecipeAdded, t }) {
  const [items, setItems]           = useState(initialItems);
  const [cursor, setCursor]         = useState(0);
  const [allCats, setAllCats]       = useState([]);
  const [allTags, setAllTags]       = useState([]);
  const [title, setTitle]           = useState('');
  const [categories, setCategories] = useState([]);
  const [tags, setTags]             = useState([]);
  const [description, setDescription] = useState('');
  const [saving, setSaving]         = useState(false);
  const [skipConfirm, setSkipConfirm] = useState(false);
  const [dupWarning, setDupWarning] = useState(null);

  // Preview pages for the current item
  const [pages, setPages]           = useState([]);
  const [pageType, setPageType]     = useState('pdf'); // 'pdf' | 'images'
  const [pagesLoading, setPagesLoading] = useState(false);

  useEffect(() => {
    fetchCategories().then(setAllCats).catch(() => {});
    fetchTags().then(setAllTags).catch(() => {});
  }, []);

  useEffect(() => {
    const item = items[cursor];
    if (!item) return;
    setTitle(item.recipe?.title || item.group_name || '');
    setCategories([]); setTags([]); setDescription(''); setSkipConfirm(false);

    setPages([]); setPagesLoading(true);
    const recipeId = item.recipe_id;
    const recipe   = item.recipe;

    if (recipe?.file_type === 'pdf') {
      setPageType('pdf');
      if (item.pdf_pages && item.pdf_pages.length > 0) {
        setPages(item.pdf_pages);
        setPagesLoading(false);
      } else {
        fetchPdfPages(recipeId)
          .then(res => setPages(res.pages || []))
          .catch(() => setPages([]))
          .finally(() => setPagesLoading(false));
      }
    } else if (recipe?.file_type === 'images' && recipe?.images?.length) {
      setPageType('images');
      setPages(recipe.images);
      setPagesLoading(false);
    } else {
      setPagesLoading(false);
    }
  }, [cursor, items]);

  // ── advance: remove the current item and move to the next one ────────────
  // FIX: setCursor must NEVER be called inside a setItems updater function.
  // Doing so causes React to process the two state updates in separate render
  // cycles, producing one frame where items has shrunk but cursor still points
  // at the old (now out-of-bounds) index. That undefined currentItem then
  // cascades into a ReferenceError crash during render.
  //
  // The correct pattern is:
  //   1. setItems — remove the finished item
  //   2. A separate useEffect clamps the cursor after every items change
  const advance = useCallback(() => {
    setItems(prev => prev.filter((_, i) => i !== cursor));
    setSaving(false);
    setDupWarning(null);
  }, [cursor]);

  // Clamp cursor after every items change so it is always a valid index.
  // This replaces the old inline setCursor-inside-setItems pattern.
  useEffect(() => {
    if (items.length === 0) {
      setCursor(0);
    } else {
      setCursor(prev => Math.min(prev, items.length - 1));
    }
  }, [items.length]);

  const doSave = async () => {
    setSaving(true); setDupWarning(null);
    try {
      await confirmImportItem(items[cursor].recipe_id, {
        title: title.trim(), categories: categories.join(','),
        tags: tags.join(','), description,
      });
      onRecipeAdded && onRecipeAdded();
      fetchCategories().then(setAllCats).catch(() => {});
      fetchTags().then(setAllTags).catch(() => {});
      advance();
    } catch (e) { setSaving(false); }
  };

  const handleSave = async () => {
    if (!title.trim()) return;
    try {
      const dupes = await checkImportDuplicate(items[cursor].recipe_id, title.trim());
      if (dupes.content_duplicates.length > 0 || dupes.title_duplicates.length > 0) {
        setDupWarning(dupes);
        return;
      }
    } catch (_) {}
    await doSave();
  };

  const handleSkip = async () => {
    try { await discardImportItem(items[cursor].recipe_id); } catch (_) {}
    advance(); setSkipConfirm(false);
  };

  const total = items.length;

  if (total === 0) {
    return (
      <div className="iw-centered">
        <CheckCircle size={48} color="var(--terracotta)" />
        <h3>{t('importDone')}</h3>
        <p className="iw-hint">{t('importDoneHint')}</p>
        <button className="iw-btn-primary" onClick={onClose}>{t('close')}</button>
      </div>
    );
  }

  const currentItem = items[cursor];

  // Safety guard: cursor and items can be briefly out of sync during the
  // React state update cycle. Return null for that single frame.
  if (!currentItem) return null;

  return (
    <>
      <div className="iw-progress-track">
        <div className="iw-progress-fill" style={{width:`${(cursor/total)*100}%`}} />
      </div>
      <div className="iw-body">
        <div className="iw-content">
          {/* Sidebar queue */}
          <div className="iw-sidebar">
            <div className="iw-sidebar-header">
              <FolderOpen size={14} />
              <span>{total} {t('importPending')}</span>
            </div>
            <div className="iw-queue-list">
              {items.map((item, i) => (
                <div key={item.recipe_id} className={`iw-queue-item ${i===cursor?'active':''}`} onClick={() => setCursor(i)}>
                  {item.recipe?.file_type === 'pdf'
                    ? <FileText size={14} className="iw-queue-icon pdf" />
                    : <Image    size={14} className="iw-queue-icon img" />
                  }
                  <span className="iw-queue-name">{item.group_name || item.recipe?.title || '…'}</span>
                </div>
              ))}
            </div>
          </div>
          {/* Edit panel */}
          <div className="iw-edit-panel">

            {/* ── Page viewer ── */}
            <div className="iw-viewer">
              {pagesLoading ? (
                <div className="iw-viewer-loading">
                  <RefreshCw size={22} className="iw-spin" />
                  <span>{t('importLoadingItem')}</span>
                </div>
              ) : pages.length > 0 ? (
                <div className="iw-viewer-scroll">
                  {pages.map((pg, i) => (
                    <ViewerPage
                      key={`${currentItem.recipe_id}-${pg}`}
                      src={pageType === 'pdf'
                        ? pdfPageUrl(currentItem.recipe_id, pg)
                        : imageUrl(currentItem.recipe_id, pg)
                      }
                      alt={`Page ${i + 1}`}
                    />
                  ))}
                </div>
              ) : (
                <div className="iw-viewer-empty">
                  {currentItem?.recipe?.file_type === 'pdf'
                    ? <FileText size={40} />
                    : <Image size={40} />
                  }
                  <span className="iw-viewer-empty-label">
                    {currentItem?.recipe?.file_type === 'pdf' ? 'PDF' : `${currentItem?.recipe?.images?.length || 0} images`}
                  </span>
                </div>
              )}
              {/* Type + counter badge overlay */}
              <div className="iw-viewer-badges">
                {currentItem?.recipe?.file_type === 'pdf'
                  ? <span className="iw-type-badge pdf">PDF</span>
                  : <span className="iw-type-badge img">{pages.length} {pages.length === 1 ? 'image' : 'images'}</span>
                }
                <span className="iw-counter-badge">{cursor + 1} / {total}</span>
              </div>
            </div>
            <div className="iw-form">
              <div className="iw-field">
                <label className="iw-label">{t('importNameLabel')} <span className="iw-required">*</span></label>
                <input type="text" className="iw-input" value={title} onChange={e=>setTitle(e.target.value)} autoFocus />
              </div>
              <PillInput label={t('categories')} values={categories} allOptions={allCats} onChange={setCategories} placeholder={t('addCategory')||'Add category…'} />
              <PillInput label={t('tags')} values={tags} allOptions={allTags} onChange={setTags} placeholder={t('addTag')||'Add tag…'} />
              <div className="iw-field">
                <label className="iw-label">{t('description')}</label>
                <textarea className="iw-textarea" rows={2} value={description} onChange={e=>setDescription(e.target.value)} placeholder={t('optionalNotes')||'Optional notes…'} />
              </div>
            </div>
            {skipConfirm && (
              <div className="iw-skip-confirm">
                <p>{t('importSkipConfirm')}</p>
                <div className="iw-skip-confirm-btns">
                  <button className="iw-btn-ghost" onClick={()=>setSkipConfirm(false)}>{t('cancel')}</button>
                  <button className="iw-btn-danger" onClick={handleSkip}>{t('importSkip')}</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      {!skipConfirm && (
        <>
          {dupWarning && (
            <div className="iw-dup-warning">
              <AlertTriangle size={16} className="dup-icon" />
              <div className="dup-warning-content">
                <strong>Possible duplicate</strong>
                {dupWarning.content_duplicates.length > 0 && (
                  <p>Same file already exists: <em>{dupWarning.content_duplicates.map(d => d.title).join(', ')}</em></p>
                )}
                {dupWarning.title_duplicates.length > 0 && (
                  <p>Same title already exists: <em>{dupWarning.title_duplicates.map(d => d.title).join(', ')}</em></p>
                )}
                <div className="dup-actions">
                  <button className="btn-sm btn-ghost" onClick={() => setDupWarning(null)}>Go back</button>
                  <button className="btn-sm btn-warning" onClick={doSave}>Save Anyway</button>
                </div>
              </div>
            </div>
          )}
          <div className="iw-footer">
            <div className="iw-footer-left">
              <button className="iw-btn-ghost" onClick={()=>setSkipConfirm(true)}><SkipForward size={15}/> {t('importSkip')}</button>
              <button className="iw-btn-ghost" onClick={onClose}><StopCircle size={15}/> {t('importStopForNow')}</button>
            </div>
            <button className="iw-btn-primary" onClick={handleSave} disabled={!title.trim()||saving}>
              {saving ? '…' : <>{t('importSaveNext')} <ChevronRight size={15}/></>}
            </button>
          </div>
        </>
      )}
    </>
  );
}

// ── Main orchestrator ─────────────────────────────────────────────────────────
export default function ImportWizard({ onClose, onRecipeAdded }) {
  const { t } = useApp();
  const [phase, setPhase]           = useState('loading');
  const [queueItems, setQueueItems] = useState([]);

  useEffect(() => {
    getImportQueue()
      .then(res => {
        if (res.items && res.items.length > 0) {
          setQueueItems(res.items); setPhase('wizard');
        } else {
          setPhase('upload');
        }
      })
      .catch(() => setPhase('upload'));
  }, []);

  return createPortal(
    <div className="iw-overlay">
      <div className={`iw-modal ${phase==='upload'?'iw-modal--upload':''}`}>
        <div className="iw-header">
          <span className="iw-header-title">{t('importWizardTitle')}</span>
          {phase === 'wizard' && queueItems.length > 0 && (
            <span className="iw-header-badge">{queueItems.length} {t('importPending')}</span>
          )}
          {phase === 'wizard' && (
            <button className="iw-btn-ghost iw-header-add-more" onClick={()=>setPhase('upload')} title={t('importAddMore')}>
              <Upload size={14}/> {t('importAddMore')}
            </button>
          )}
          <button className="iw-close" onClick={onClose}><X size={18}/></button>
        </div>

        {phase === 'loading' && (
          <div className="iw-centered"><RefreshCw size={28} className="iw-spin"/><p>{t('loading')||'Loading…'}</p></div>
        )}
        {phase === 'upload' && (
          <UploadPhase onGroupsReady={items => { setQueueItems(items); setPhase('wizard'); }} onClose={onClose} t={t} />
        )}
        {phase === 'wizard' && (
          <WizardErrorBoundary>
            <WizardPhase initialItems={queueItems} onClose={onClose} onRecipeAdded={onRecipeAdded} t={t} />
          </WizardErrorBoundary>
        )}
      </div>
    </div>,
    document.body
  );
}
