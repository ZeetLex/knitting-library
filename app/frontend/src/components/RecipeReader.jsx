import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
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

export default function RecipeReader({ content, formatVersion = 'legacy', legacyView }) {
  const { t } = useApp();
  const prefix = useId().replace(/:/g, '');
  const [enhanced, setEnhanced] = useState(formatVersion === 'gfm-v1');
  const [size, setSize] = useState(18);
  const [spacing, setSpacing] = useState('1.75');
  const [focus, setFocus] = useState(false);
  const container = useRef(null);
  const headings = useMemo(() => readerHeadings(content), [content]);
  useEffect(() => { setEnhanced(formatVersion === 'gfm-v1'); }, [formatVersion]);
  useEffect(() => {
    if (!focus) return undefined;
    const previousFocus = document.activeElement;
    const escape = e => {
      if (e.key === 'Escape') setFocus(false);
      if (e.key === 'Tab') {
        const items = [...container.current.querySelectorAll('button,a[href],input,select,summary,[tabindex="0"]')];
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
    <div className="recipe-reader-controls">
      <label>{t('readerTextSize')} <input aria-label={t('readerTextSize')} type="range" min="14" max="26" value={size} onChange={e => setSize(Number(e.target.value))} /></label>
      <label>{t('readerSpacing')} <select value={spacing} onChange={e => setSpacing(e.target.value)}>
        <option value="1.5">{t('readerCompact')}</option><option value="1.75">{t('readerComfortable')}</option><option value="2">{t('readerSpacious')}</option>
      </select></label>
      {legacyView && formatVersion !== 'gfm-v1' && <button type="button" className="btn-secondary" aria-pressed={enhanced} onClick={() => setEnhanced(!enhanced)}>{t('readerEnhanced')}</button>}
      <button type="button" className="btn-secondary" aria-pressed={focus} onClick={() => setFocus(!focus)}>{t(focus ? 'readerExitFocus' : 'readerFocus')}</button>
    </div>
    {enhanced && headings.length > 1 && <details className="recipe-reader-contents"><summary>{t('readerContents')}</summary><nav aria-label={t('readerContents')}>
      {headings.map(heading => <a key={heading.line} style={{ paddingInlineStart: `${(heading.depth - 1) * 12}px` }} href={`#${prefix}-${heading.line}`}>{heading.label}</a>)}
    </nav></details>}
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
