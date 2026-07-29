import React from 'react';
import { useApp } from '../utils/AppContext';
import './AppBrand.css';

export default function AppBrand({ variant = 'shell', compact = false }) {
  const { branding } = useApp();
  const title = branding?.title || 'Knitting Library';
  const iconUrl = branding?.icon_url || '/brand-logo.png';

  return (
    <div className={`brand-mark brand-mark--${variant} ${compact ? 'brand-mark--compact' : ''}`}>
      <img className="brand-mark-icon" src={iconUrl} alt="" aria-hidden="true" />
      {!compact && <span className="brand-mark-title" title={title}>{title}</span>}
    </div>
  );
}
