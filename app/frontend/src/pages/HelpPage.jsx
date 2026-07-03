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
  ArrowRight, Info, ExternalLink, FileText,
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
        { labelKey: 'helpLabelSignIn',        key: 'helpS1SignIn' },
        { labelKey: 'helpLabelHomeDashboard', key: 'helpS1Home' },
        { labelKey: 'helpLabelNavigation',    key: 'helpS1Nav' },
        { labelKey: 'helpLabelHomeShortcut',  key: 'helpS1Logo' },
      ],
    },
    {
      id: 's2',
      icon: <Search size={20} />,
      titleKey: 'helpS2Title',
      items: [
        { key: 'helpS2Intro' },
        { labelKey: 'helpLabelAddingRecipes', key: 'helpS2Add' },
        { labelKey: 'helpLabelSearchFilters', key: 'helpS2Search' },
        { labelKey: 'helpLabelGridSizes',     key: 'helpS2Grid' },
        { labelKey: 'categories',             key: 'helpS2Categories' },
        { labelKey: 'tags',                   key: 'helpS2Tags' },
      ],
    },
    {
      id: 's3',
      icon: <Eye size={20} />,
      titleKey: 'helpS3Title',
      items: [
        { key: 'helpS3Intro' },
        { labelKey: 'helpLabelPdfRecipes',     key: 'helpS3PDF' },
        { labelKey: 'helpLabelImageRecipes',   key: 'helpS3Images' },
        { labelKey: 'helpLabelDownload',       key: 'helpS3Download' },
        { labelKey: 'helpLabelEditingDetails', key: 'helpS3Edit' },
        { labelKey: 'helpLabelMobileLayout',   key: 'helpS3Mobile' },
      ],
    },
    {
      id: 's4',
      icon: <PenTool size={20} />,
      titleKey: 'helpS4Title',
      items: [
        { key: 'helpS4Intro' },
        { labelKey: 'helpLabelAnnotations', key: 'helpS4Annotate' },
        { labelKey: 'helpLabelRowCounter',  key: 'helpS4RowCounter' },
        { labelKey: 'helpLabelIncreaseDecrease', key: 'helpS4IncreaseDecrease' },
        { labelKey: 'helpLabelSavedRows',   key: 'helpS4SaveRow' },
        { labelKey: 'toolNotes',            key: 'helpS4Notes' },
      ],
    },
    {
      id: 's5',
      icon: <Activity size={20} />,
      titleKey: 'helpS5Title',
      items: [
        { key: 'helpS5Intro' },
        { labelKey: 'helpLabelStartingProject', key: 'helpS5Start' },
        { labelKey: 'helpLabelFinishing',       key: 'helpS5Finish' },
        { labelKey: 'helpLabelSessionHistory',  key: 'helpS5History' },
        { labelKey: 'helpLabelStatusFilter',    key: 'helpS5Filter' },
      ],
    },
    {
      id: 's6',
      icon: <Package size={20} />,
      titleKey: 'helpS6Title',
      items: [
        { key: 'helpS6Intro' },
        { labelKey: 'helpLabelAddingYarn',     key: 'helpS6Add' },
        { labelKey: 'helpLabelAutoFillUrl',    key: 'helpS6URL' },
        { labelKey: 'helpLabelColourVariants', key: 'helpS6Colours' },
      ],
    },
    {
      id: 's7',
      icon: <Package size={20} />,
      titleKey: 'helpS7Title',
      items: [
        { key: 'helpS7Intro' },
        { labelKey: 'helpLabelAddingItems',     key: 'helpS7Add' },
        { labelKey: 'helpLabelAdjustingStock',  key: 'helpS7Adjust' },
        { labelKey: 'helpLabelLinkingProjects', key: 'helpS7Link' },
        { labelKey: 'helpLabelAdjustmentLog',   key: 'helpS7Log' },
      ],
    },
    {
      id: 's8',
      icon: <Upload size={20} />,
      titleKey: 'helpS8Title',
      items: [
        { key: 'helpS8Intro' },
        { labelKey: 'helpLabelHowToImport', key: 'helpS8How' },
        { labelKey: 'helpLabelWizard',      key: 'helpS8Wizard' },
      ],
    },
    {
      id: 's9',
      icon: <Scissors size={20} />,
      titleKey: 'helpS9Title',
      items: [
        { key: 'helpS9Intro' },
        { labelKey: 'helpLabelRotate',          key: 'helpS9Rotate' },
        { labelKey: 'helpLabelPerspectiveCrop', key: 'helpS9Crop' },
        { labelKey: 'helpLabelReorderPages',    key: 'helpS9Reorder' },
      ],
    },
    {
      id: 's10',
      icon: <FileText size={20} />,
      titleKey: 'helpS10TextTitle',
      items: [
        { key: 'helpS10TextIntro' },
        { labelKey: 'helpLabelTextVersionOpen', key: 'helpS10TextOpen' },
        { labelKey: 'helpLabelTextVersionCreate', key: 'helpS10TextCreate' },
        { labelKey: 'helpLabelTextVersionReview', key: 'helpS10TextReview' },
        { labelKey: 'helpLabelAISetup', key: 'helpS10TextAISetup' },
        { labelKey: 'helpLabelPromptLanguage', key: 'helpS10TextPrompt' },
      ],
    },
    {
      id: 's11',
      icon: <Settings size={20} />,
      titleKey: 'helpS10Title',
      items: [
        { key: 'helpS10Intro' },
        { labelKey: 'appearance',             key: 'helpS10Appearance' },
        { labelKey: 'language',               key: 'helpS10Language' },
        { labelKey: 'currency',               key: 'helpS10Currency' },
        { labelKey: 'password',               key: 'helpS10Password' },
        { labelKey: 'helpLabelTwoFactorAuth', key: 'helpS10TwoFA' },
        { labelKey: 'statistics',             key: 'helpS10Stats' },
      ],
    },
  ];
}

// ── Main component ────────────────────────────────────────────────────────────
const ISSUES_URL = 'https://github.com/ZeetLex/knitting-library/issues';

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
              <a
                className="help-issue-link"
                href={ISSUES_URL}
                target="_blank"
                rel="noopener noreferrer"
              >
                <span>{t('helpIssueLink')}</span>
                <ExternalLink size={14} />
              </a>
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
                      <div key={j} className={`help-item ${item.labelKey ? 'help-item--labelled' : 'help-item--intro'}`}>
                        {item.labelKey && (
                          <div className="help-item-label">
                            <ArrowRight size={13} />
                            <span>{t(item.labelKey)}</span>
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
            <span>{t('happyKnitting')}</span>
          </div>
        </article>
      </div>
    </div>
  );
}
