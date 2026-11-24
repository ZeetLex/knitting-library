import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { List, Maximize2, Minimize2, MoreHorizontal, AlertTriangle } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { safeReaderUrl, readerHeadings, preserveInstructionNumbers, formatSelection } from '../utils/readerPolicy.mjs';
import './RecipeReader.css';

export function RecipeMarkdown({ content, prefix = 'recipe' }) {
  const origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin;
  const headings = {};
  for (let level = 1; level <= 6; level++) {
    const Tag = `h${level}`;
    headings[Tag] = ({ node, children }) => <Tag id={`${prefix}-${node.position?.start.line}`}>{children}</Tag>;
  }
  return <div className="recipe-markdown"><ReactMarkdown skipHtml
    remarkPlugins={[[remarkGfm, { singleTilde: false }], remarkBreaks, preserveInstructionNumbers]}
    urlTransform={(url, key) => safeReaderUrl(url, key === 'src', origin)}
    components={{ ...headings,
      table: ({ children }) => <div className="recipe-table-scroll" tabIndex={0}><table>{children}</table></div>,
      a: ({ href, children }) => href ? <a href={href} target={href.startsWith('#') ? undefined : '_blank'} rel="noopener noreferrer">{children}</a> : <span>{children}</span>,
      img: ({ src, alt }) => src ? <img src={src} alt={alt || ''} loading="lazy" /> : <span>{alt}</span>,
    }}>{content || ''}</ReactMarkdown></div>;
}

export default function RecipeReader({ content, formatVersion = 'legacy', legacyView, documentControls, outdated = false }) {
  const { t } = useApp();
  const prefix = useId().replace(/:/g, '');
  const [enhanced, setEnhanced] = useState(true);
  const [panel, setPanel] = useState(null);
  const [size, setSize] = useState(18);
  const [spacing, setSpacing] = useState('1.75');
  const [focus, setFocus] = useState(false);
  const container = useRef(null);
  const headings = useMemo(() => readerHeadings(content), [content]);
  useEffect(() => { setEnhanced(true); setPanel(null); }, [content, formatVersion]);
  useEffect(() => {
    if (!focus) return undefined;
    const previousFocus = document.activeElement;
    const escape = e => {
      if (e.key === 'Escape') setFocus(false);
      if (e.key === 'Tab') {
        const items = [...container.current.querySelectorAll('button,a[href],input,select,summary,[tabindex="0"]')].filter(item => !item.disabled && item.getClientRects().length);
        const first = items[0], last = items.at(-1);
        if (e.shiftKey && (document.activeElement === first || document.activeElement === container.current)) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    container.current?.focus();
    window.addEventListener('keydown', escape);
    return () => { window.removeEventListener('keydown', escape); previousFocus?.focus(); };
  }, [focus]);
  return <section ref={container} tabIndex={-1} className={`recipe-reader ${focus ? 'recipe-reader--focus' : ''}`}
    style={{ '--reader-size': `${size}px`, '--reader-spacing': spacing }} aria-label={t('recipeReader')}>
    <div className="recipe-reader-controls" onKeyDown={e => {
      if (e.key === 'Escape' && panel) {
        e.stopPropagation();
        container.current?.querySelector(`[data-reader-panel="${panel}"]`)?.focus();
        setPanel(null);
      }
    }}>
      <div className="recipe-reader-bar">
        <span className="recipe-reader-title">{t('textVersion')}</span>
        {outdated && <button type="button" className="recipe-reader-stale" title={t('textVersionOutdated')} aria-label={t('textVersionOutdated')}
          aria-expanded={panel === 'document'} aria-controls={`${prefix}-document`} onClick={() => setPanel(panel === 'document' ? null : 'document')}><AlertTriangle size={17} /></button>}
        <div className="recipe-reader-tools">
          {enhanced && headings.length > 1 && <button type="button" data-reader-panel="contents" aria-label={t('readerContents')} title={t('readerContents')}
            aria-expanded={panel === 'contents'} aria-controls={`${prefix}-contents`} onClick={() => setPanel(panel === 'contents' ? null : 'contents')}><List size={19} /></button>}
          <button type="button" data-reader-panel="appearance" aria-label={t('readerSettings')} title={t('readerSettings')}
            aria-expanded={panel === 'appearance'} aria-controls={`${prefix}-appearance`} onClick={() => setPanel(panel === 'appearance' ? null : 'appearance')}><span className="recipe-reader-aa">Aa</span></button>
          <button type="button" aria-label={t(focus ? 'readerExitFocus' : 'readerFocus')} title={t(focus ? 'readerExitFocus' : 'readerFocus')}
            aria-pressed={focus} onClick={() => { setPanel(null); setFocus(!focus); }}>{focus ? <Minimize2 size={18} /> : <Maximize2 size={18} />}</button>
          {documentControls && <button type="button" data-reader-panel="document" aria-label={t('readerDocumentActions')} title={t('readerDocumentActions')}
            aria-expanded={panel === 'document'} aria-controls={`${prefix}-document`} onClick={() => setPanel(panel === 'document' ? null : 'document')}><MoreHorizontal size={21} /></button>}
        </div>
      </div>
      <div hidden={panel !== 'appearance'} id={`${prefix}-appearance`} className="recipe-reader-settings">
        <label>{t('readerTextSize')} <input aria-label={t('readerTextSize')} type="range" min="14" max="26" value={size} onChange={e => setSize(Number(e.target.value))} /></label>
        <label>{t('readerSpacing')} <select value={spacing} onChange={e => setSpacing(e.target.value)}>
          <option value="1.5">{t('readerCompact')}</option><option value="1.75">{t('readerComfortable')}</option><option value="2">{t('readerSpacious')}</option>
        </select></label>
        {legacyView && formatVersion !== 'gfm-v1' && <button type="button" className="btn-secondary" aria-pressed={enhanced} onClick={() => setEnhanced(!enhanced)}>{t('readerEnhanced')}</button>}
      </div>
      {enhanced && headings.length > 1 && <nav hidden={panel !== 'contents'} id={`${prefix}-contents`} className="recipe-reader-contents" aria-label={t('readerContents')}>
        {headings.map(heading => <a key={heading.line} style={{ paddingInlineStart: `${(heading.depth - 1) * 12}px` }} href={`#${prefix}-${heading.line}`} onClick={() => setPanel(null)}>{heading.label}</a>)}
      </nav>}
      {documentControls && <div hidden={panel !== 'document'} id={`${prefix}-document`} className="recipe-reader-document">{documentControls}</div>}
    </div>
    {enhanced || !legacyView ? <RecipeMarkdown content={content} prefix={prefix} /> : legacyView}
  </section>;
}

export function RecipeTextEditor({ value, onChange, className = '', dirty = false, navigationKey, initialPreview = true }) {
  const { t } = useApp();
  const [preview, setPreview] = useState(initialPreview);
  const input = useRef(null);
  const previousKey = useRef(navigationKey);
  const [pendingNavigation, setPendingNavigation] = useState(null);
  const navigationAllowed = useRef(false);
  const dialog = useRef(null);
  useEffect(() => {
    if (!dirty) return undefined;
    const beforeUnload = e => { e.preventDefault(); e.returnValue = ''; };
    const confirmNavigation = e => {
      const target = e.target.closest('button,a,[role="button"]');
      if (!navigationAllowed.current && target && (target.hasAttribute('data-recipe-leave') || !target.closest('[data-recipe-editor-scope]'))) {
        e.preventDefault(); e.stopImmediatePropagation();
        setPendingNavigation(target);
      }
    };
    window.addEventListener('beforeunload', beforeUnload);
    document.addEventListener('click', confirmNavigation, true);
    return () => { window.removeEventListener('beforeunload', beforeUnload); document.removeEventListener('click', confirmNavigation, true); };
  }, [dirty, t]);
  useEffect(() => {
    if (!pendingNavigation) return undefined;
    dialog.current?.querySelector('button')?.focus();
    const keydown = e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setPendingNavigation(null); input.current?.focus(); }
      if (e.key === 'Tab') {
        const items = [...dialog.current.querySelectorAll('button')];
        if ((e.shiftKey && document.activeElement === items[0]) || (!e.shiftKey && document.activeElement === items.at(-1))) {
          e.preventDefault(); (e.shiftKey ? items.at(-1) : items[0]).focus();
        }
      }
    };
    document.addEventListener('keydown', keydown, true);
    return () => document.removeEventListener('keydown', keydown, true);
  }, [pendingNavigation]);
  useEffect(() => { if (previousKey.current !== navigationKey) { setPreview(true); previousKey.current = navigationKey; } }, [navigationKey]);
  const apply = kind => {
    const start = input.current?.selectionStart ?? value.length;
    const end = input.current?.selectionEnd ?? start;
    onChange(formatSelection(value, start, end, kind));
    input.current?.focus();
  };
  return <div className="recipe-text-editor">
    {pendingNavigation && <div className="reader-unsaved-backdrop"><div ref={dialog} role="dialog" aria-modal="true" aria-label={t('readerUnsaved')} className="reader-unsaved-dialog">
      <p>{t('readerUnsaved')}</p>
      <button type="button" className="btn-primary" onClick={() => { setPendingNavigation(null); input.current?.focus(); }}>{t('cancel')}</button>
      <button type="button" className="btn-secondary" onClick={() => {
        const target = pendingNavigation;
        setPendingNavigation(null);
        navigationAllowed.current = true;
        if (target.isConnected) target.click();
        navigationAllowed.current = false;
      }}>{t('discard')}</button>
    </div></div>}
    <div className="recipe-editor-toolbar" role="group" aria-label={t('readerEditor')}>
      <button type="button" className="btn-secondary" aria-pressed={preview} onClick={() => setPreview(true)}>{t('readerPreview')}</button>
      <button type="button" className="btn-secondary" aria-pressed={!preview} onClick={() => setPreview(false)}>{t('edit')}</button>
      {!preview && ['heading', 'bold', 'list', 'table'].map(kind => <button type="button" className="btn-secondary" key={kind} onClick={() => apply(kind)}>{t(`readerFormat_${kind}`)}</button>)}
    </div>
    {preview ? <RecipeMarkdown content={value} prefix="recipe-edit-preview" /> : <><p className="settings-row-sub">{t('readerSourceHint')}</p>
      <textarea ref={input} className={className} aria-label={t('readerEditor')} value={value} onChange={e => onChange(e.target.value)} /></>}
  </div>;
}
