import React, { useEffect, useRef, useState } from 'react';
import { ArrowUp, ChevronDown, Search, X } from 'lucide-react';
import './CollectionToolbar.css';

export default function CollectionToolbar({
  title,
  subtitle,
  searchValue,
  onSearchChange,
  placeholder,
  searchLabel,
  searchType = 'search',
  datalistId,
  datalistOptions = [],
  fieldOptions = [],
  fieldValue = '',
  onFieldChange,
  filterButton,
  viewOptions = [],
  viewValue,
  onViewChange,
  actions = [],
  children,
  compactSearch = false,
}) {
  const [fieldOpen, setFieldOpen] = useState(false);
  const [compactVisible, setCompactVisible] = useState(false);
  const fieldRef = useRef(null);
  const toolbarRef = useRef(null);
  const currentField = fieldOptions.find(option => option.key === fieldValue) || fieldOptions[0];
  const hasFieldSelector = fieldOptions.length > 0 && onFieldChange;

  useEffect(() => {
    if (!hasFieldSelector) return undefined;
    const close = (event) => {
      if (fieldRef.current && !fieldRef.current.contains(event.target)) setFieldOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [hasFieldSelector]);

  useEffect(() => {
    if (!compactSearch) return undefined;

    const updateCompactVisibility = () => {
      const toolbar = toolbarRef.current;
      if (!toolbar) return;
      setCompactVisible(toolbar.getBoundingClientRect().bottom < 0);
    };

    updateCompactVisibility();
    window.addEventListener('scroll', updateCompactVisibility, { passive: true });
    window.addEventListener('resize', updateCompactVisibility);
    return () => {
      window.removeEventListener('scroll', updateCompactVisibility);
      window.removeEventListener('resize', updateCompactVisibility);
    };
  }, [compactSearch]);

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div
      ref={toolbarRef}
      className={`collection-toolbar ${compactSearch ? 'collection-toolbar--compact-source' : ''}`}
    >
      <div className="collection-toolbar-inner">
        {title && (
          <div className="collection-toolbar-heading">
            <h1>{title}</h1>
            {subtitle && <p>{subtitle}</p>}
          </div>
        )}

        <div className={`collection-search ${hasFieldSelector ? 'collection-search--with-field' : ''}`}>
          {hasFieldSelector && (
            <div className="collection-field" ref={fieldRef}>
              <button
                type="button"
                className="collection-field-btn"
                onClick={() => setFieldOpen(open => !open)}
                aria-expanded={fieldOpen}
              >
                <span>{currentField?.label}</span>
                <ChevronDown size={13} className={fieldOpen ? 'rotated' : ''} />
              </button>
              {fieldOpen && (
                <div className="collection-field-menu">
                  {fieldOptions.map(option => (
                    <button
                      type="button"
                      key={option.key}
                      className={`collection-field-option ${fieldValue === option.key ? 'active' : ''}`}
                      onClick={() => {
                        onFieldChange(option.key);
                        setFieldOpen(false);
                      }}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {hasFieldSelector && <span className="collection-search-divider" />}

          <div className="collection-search-input-wrap">
            <Search size={17} className="collection-search-icon" />
            <input
              list={datalistId}
              type={searchType}
              className="collection-search-input"
              placeholder={placeholder}
              value={searchValue}
              onChange={event => onSearchChange(event.target.value)}
              aria-label={searchLabel || placeholder}
            />
            {datalistId && datalistOptions.length > 0 && (
              <datalist id={datalistId}>
                {datalistOptions.map(option => <option key={option} value={option} />)}
              </datalist>
            )}
            {searchValue && (
              <button
                type="button"
                className="collection-search-clear"
                onClick={() => onSearchChange('')}
                aria-label="Clear search"
              >
                <X size={16} />
              </button>
            )}
          </div>
        </div>

        <div className="collection-toolbar-rail" aria-label="Collection controls">
          {filterButton}

          {viewOptions.length > 0 && (
            <div className="collection-view-switcher">
              {viewOptions.map(option => (
                <button
                  type="button"
                  key={option.key}
                  className={`collection-view-btn ${viewValue === option.key ? 'active' : ''}`}
                  onClick={() => onViewChange(option.key)}
                  title={option.label}
                  aria-label={option.label}
                  aria-pressed={viewValue === option.key}
                >
                  {option.icon}
                </button>
              ))}
            </div>
          )}

          {actions.map(action => (
            <button
              type="button"
              key={action.key}
              className={`collection-action ${action.variant === 'secondary' ? 'collection-action--secondary' : ''} ${action.active ? 'active' : ''}`}
              onClick={action.onClick}
              title={action.title || action.label}
              aria-pressed={action.active || undefined}
            >
              {action.icon}
              <span>{action.label}</span>
            </button>
          ))}
        </div>
      </div>
      {children}
      {compactSearch && (
        <div className={`collection-compact-search ${compactVisible ? 'visible' : ''}`} aria-hidden={!compactVisible}>
          <div className="collection-compact-search-inner">
            <Search size={17} className="collection-compact-search-icon" />
            <input
              type={searchType}
              className="collection-compact-search-input"
              placeholder={placeholder}
              value={searchValue}
              onChange={event => onSearchChange(event.target.value)}
              aria-label={searchLabel || placeholder}
              tabIndex={compactVisible ? 0 : -1}
            />
            {searchValue && (
              <button
                type="button"
                className="collection-compact-search-clear"
                onClick={() => onSearchChange('')}
                aria-label="Clear search"
                tabIndex={compactVisible ? 0 : -1}
              >
                <X size={15} />
              </button>
            )}
            <button
              type="button"
              className="collection-compact-top"
              onClick={scrollToTop}
              aria-label="Back to top"
              title="Back to top"
              tabIndex={compactVisible ? 0 : -1}
            >
              <ArrowUp size={18} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
