/**
 * HelpPage.js
 * Wikipedia-style help and guide for end users.
 * Covers all user-facing features. No admin-only content.
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  ChevronLeft, ChevronDown, ChevronRight,
  BookOpen, Search, Eye, PenTool, Activity,
  Package, Upload, Scissors, Settings,
  ArrowRight, Info,
} from 'lucide-react';
import { useApp } from '../utils/AppContext';
import './HelpPage.css';

// ── Section definitions ───────────────────────────────────────────────────────
// Each section has an id, a translation-key for the title, an icon, and an array of items.
// Items are rendered as labelled paragraphs.

function useSections(t) {
  return [
    {
      id: 's1',
      icon: <BookOpen size={20} />,
      titleKey: 'helpS1Title',
      items: [
        { key: 'helpS1Intro' },
        { label: 'Sign in',          key: 'helpS1SignIn' },
        { label: 'Navigation',        key: 'helpS1Nav' },
        { label: 'Logo shortcut',     key: 'helpS1Logo' },
      ],
    },
    {
      id: 's2',
      icon: <Search size={20} />,
      titleKey: 'helpS2Title',
      items: [
        { key: 'helpS2Intro' },
        { label: 'Adding recipes',    key: 'helpS2Add' },
        { label: 'Search & filters',  key: 'helpS2Search' },
        { label: 'Grid sizes',        key: 'helpS2Grid' },
        { label: 'Categories',        key: 'helpS2Categories' },
        { label: 'Tags',              key: 'helpS2Tags' },
      ],
    },
    {
      id: 's3',
      icon: <Eye size={20} />,
      titleKey: 'helpS3Title',
      items: [
        { key: 'helpS3Intro' },
        { label: 'PDF recipes',       key: 'helpS3PDF' },
        { label: 'Image recipes',     key: 'helpS3Images' },
        { label: 'Download',          key: 'helpS3Download' },
        { label: 'Editing details',   key: 'helpS3Edit' },
        { label: 'Mobile layout',     key: 'helpS3Mobile' },
      ],
    },
    {
      id: 's4',
      icon: <PenTool size={20} />,
      titleKey: 'helpS4Title',
      items: [
        { key: 'helpS4Intro' },
        { label: 'Annotations',       key: 'helpS4Annotate' },
        { label: 'Row counter',       key: 'helpS4RowCounter' },
        { label: 'Saved rows',        key: 'helpS4SaveRow' },
        { label: 'Notes',             key: 'helpS4Notes' },
      ],
    },
    {
      id: 's5',
      icon: <Activity size={20} />,
      titleKey: 'helpS5Title',
      items: [
        { key: 'helpS5Intro' },
        { label: 'Starting a project', key: 'helpS5Start' },
        { label: 'Finishing',          key: 'helpS5Finish' },
        { label: 'Session history',    key: 'helpS5History' },
        { label: 'Status filter',      key: 'helpS5Filter' },
      ],
    },
    {
      id: 's6',
      icon: <Package size={20} />,
      titleKey: 'helpS6Title',
      items: [
        { key: 'helpS6Intro' },
        { label: 'Adding yarn',        key: 'helpS6Add' },
        { label: 'Auto-fill from URL', key: 'helpS6URL' },
        { label: 'Colour variants',    key: 'helpS6Colours' },
      ],
    },
    {
      id: 's7',
      icon: <Package size={20} />,
      titleKey: 'helpS7Title',
      items: [
        { key: 'helpS7Intro' },
        { label: 'Adding items',       key: 'helpS7Add' },
        { label: 'Adjusting stock',    key: 'helpS7Adjust' },
        { label: 'Linking to projects',key: 'helpS7Link' },
        { label: 'Adjustment log',     key: 'helpS7Log' },
      ],
    },
    {
      id: 's8',
      icon: <Upload size={20} />,
      titleKey: 'helpS8Title',
      items: [
        { key: 'helpS8Intro' },
        { label: 'How to import',      key: 'helpS8How' },
        { label: 'The wizard',         key: 'helpS8Wizard' },
      ],
    },
    {
      id: 's9',
      icon: <Scissors size={20} />,
      titleKey: 'helpS9Title',
      items: [
        { key: 'helpS9Intro' },
        { label: 'Rotate',             key: 'helpS9Rotate' },
        { label: 'Perspective crop',   key: 'helpS9Crop' },
        { label: 'Reorder pages',      key: 'helpS9Reorder' },
      ],
    },
    {
      id: 's10',
      icon: <Settings size={20} />,
      titleKey: 'helpS10Title',
      items: [
        { key: 'helpS10Intro' },
        { label: 'Appearance',         key: 'helpS10Appearance' },
        { label: 'Language',           key: 'helpS10Language' },
        { label: 'Currency',           key: 'helpS10Currency' },
        { label: 'Password',           key: 'helpS10Password' },
        { label: 'Two-factor auth',    key: 'helpS10TwoFA' },
        { label: 'Statistics',         key: 'helpS10Stats' },
      ],
    },
  ];
}

// ── Main component ────────────────────────────────────────────────────────────
export default function HelpPage({ onBack }) {
  const { t } = useApp();
  const sections = useSections(t);
  const [activeId, setActiveId] = useState(null); // null = all expanded on mobile
  const [expandedIds, setExpandedIds] = useState(() => new Set(sections.map(s => s.id)));
  const contentRef = useRef(null);
  const sectionRefs = useRef({});

  // Register section refs for scroll-to
  const registerRef = (id) => (el) => { sectionRefs.current[id] = el; };

  const scrollToSection = (id) => {
    setActiveId(id);
    // Expand on mobile accordion
    setExpandedIds(prev => { const next = new Set(prev); next.add(id); return next; });
    requestAnimationFrame(() => {
      const el = sectionRefs.current[id];
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  const toggleSection = (id) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Track active section on scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) setActiveId(entry.target.dataset.sectionId);
        });
      },
      { rootMargin: '-20% 0px -70% 0px', threshold: 0 }
    );
    Object.entries(sectionRefs.current).forEach(([, el]) => { if (el) observer.observe(el); });
    return () => observer.disconnect();
  }, []); // intentional — refs are populated synchronously

  return (
    <div className="help-page">
      {/* ── Top bar ── */}
      <div className="help-topbar">
        <button className="help-back" onClick={onBack} aria-label={t('backToLibrary')}>
          <ChevronLeft size={20} />
          <span>{t('backToLibrary')}</span>
        </button>
        <h2 className="help-topbar-title">{t('helpTitle')}</h2>
        <div className="help-topbar-spacer" />
      </div>

      {/* ── Body: sidebar TOC + article ── */}
      <div className="help-body">

        {/* ── Left sidebar — table of contents ── */}
        <aside className="help-toc">
          <div className="help-toc-header">
            <Info size={15} />
            <span>{t('helpTocTitle')}</span>
          </div>
          <nav>
            {sections.map((s, i) => (
              <button
                key={s.id}
                className={`help-toc-item ${activeId === s.id ? 'active' : ''}`}
                onClick={() => scrollToSection(s.id)}
              >
                <span className="help-toc-num">{i + 1}</span>
                <span className="help-toc-label">{t(s.titleKey)}</span>
                <ChevronRight size={14} className="help-toc-arrow" />
              </button>
            ))}
          </nav>
        </aside>

        {/* ── Article content ── */}
        <article className="help-article" ref={contentRef}>
          {/* Hero intro */}
          <div className="help-hero">
            <div className="help-hero-icon">🧶</div>
            <div>
              <h1 className="help-hero-title">{t('helpTitle')}</h1>
              <p className="help-hero-intro">{t('helpIntro')}</p>
            </div>
          </div>

          {/* Sections */}
          {sections.map((section, i) => {
            const expanded = expandedIds.has(section.id);
            return (
              <section
                key={section.id}
                className="help-section"
                data-section-id={section.id}
                ref={registerRef(section.id)}
              >
                {/* Section heading — acts as accordion toggle on mobile */}
                <button
                  className="help-section-heading"
                  onClick={() => toggleSection(section.id)}
                  aria-expanded={expanded}
                >
                  <span className="help-section-num">{i + 1}</span>
                  <span className="help-section-icon">{section.icon}</span>
                  <span className="help-section-title">{t(section.titleKey)}</span>
                  <ChevronDown
                    size={18}
                    className={`help-section-chevron ${expanded ? 'open' : ''}`}
                  />
                </button>

                {/* Section body — outer div handles grid-template-rows animation */}
                <div className={`help-section-body ${expanded ? 'expanded' : ''}`}>
                  {/* Inner wrapper needed for overflow:hidden to work with grid animation */}
                  <div className="help-section-body-inner">
                    {section.items.map((item, j) => (
                      <div key={j} className={`help-item ${item.label ? 'help-item--labelled' : 'help-item--intro'}`}>
                        {item.label && (
                          <div className="help-item-label">
                            <ArrowRight size={13} />
                            <span>{item.label}</span>
                          </div>
                        )}
                        <p className="help-item-text">{t(item.key)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            );
          })}

          {/* Footer note */}
          <div className="help-footer-note">
            <span>🧶</span>
            <span>Happy knitting!</span>
          </div>
        </article>
      </div>
    </div>
  );
}
