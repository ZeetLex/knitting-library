import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { FileText, Image, Maximize2 } from 'lucide-react';
import { recipeReadingViews } from '../utils/recipeToolbar.mjs';
import './RecipeToolbar.css';

export default function RecipeToolbar({ recipe, showText, activeView, onSelect, onFullscreen, t, suspended = false }) {
  const expandedRef = useRef(null);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const element = expandedRef.current;
    const root = element?.closest('[data-recipe-scroll]');
    if (!root) return undefined;
    const observer = new IntersectionObserver(([entry]) => {
      setCompact(!entry.isIntersecting && entry.rootBounds != null && entry.boundingClientRect.bottom <= entry.rootBounds.top);
    }, { root, threshold: 0 });
    observer.observe(element);
    return () => observer.disconnect();
  }, [activeView]);
  const views = recipeReadingViews(recipe, showText);
  const label = view => view === 'pdf' ? 'PDF' : view === 'images' ? t('imagesView')
    : view === 'text' ? t('readingTextView') : t('originalView');
  const controls = small => <div className="recipe-reading-controls" role="group" aria-label={t('recipeViewTabs')}>
    {views.map(view => {
      const Icon = view === 'images' || view === 'original' ? Image : FileText;
      return views.length === 1 ? <span className="recipe-reading-label" key={view}><Icon size={17} />{label(view)}</span>
        : <button type="button" key={view} aria-pressed={activeView === view} onClick={() => onSelect(view)}>
          {!small && <Icon size={17} />}<span>{label(view)}</span>
        </button>;
    })}
    {activeView !== 'text' && <button type="button" className="recipe-reading-fullscreen" onClick={onFullscreen}
      aria-label={t('openFull')} title={t('openFull')}><Maximize2 size={19} /></button>}
  </div>;
  return <>
    <div ref={expandedRef} className="recipe-reading-expanded" inert={suspended || compact ? '' : undefined}>{controls(false)}</div>
    {compact && !suspended && createPortal(<div className="recipe-reading-compact">{controls(true)}</div>, document.body)}
  </>;
}
