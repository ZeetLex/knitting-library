/**
 * AppContext.js
 * Global state that every component in the app can read.
 * Stores: logged-in user, theme (light/dark), language (en/no/hu), currency (NOK/USD/GBP/HUF/EUR), background
 *
 * Usage in any component:
 *   const { user, theme, language, currency, currencySymbol, t, login, logout } = useApp();
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useT } from './translations';

const AppContext = createContext(null);

// Map currency code → symbol
export const CURRENCY_SYMBOLS = { NOK: 'kr', USD: '$', GBP: '£', HUF: 'Ft', EUR: '€' };
export const CURRENCIES = [
  { code: 'NOK', label: 'kr — Norwegian Krone' },
  { code: 'USD', label: '$ — US Dollar' },
  { code: 'GBP', label: '£ — British Pound' },
  { code: 'HUF', label: 'Ft — Hungarian Forint' },
  { code: 'EUR', label: '€ — Euro' },
];

function normalizeBackground(background) {
  return background === 'floral' || background === 'floral-light' || background === 'floral-dark'
    ? 'default'
    : background;
}

export function AppProvider({ children }) {
  const [user, setUser]               = useState(null);
  const [theme, setTheme]             = useState('light');
  const [colourTheme, setColourTheme] = useState('terracotta');
  const [background, setBackground]   = useState('default');
  const [language, setLanguage]       = useState('en');
  const [currency, setCurrency]       = useState('NOK');
  const [loading, setLoading]         = useState(true);
  const [setupRequired, setSetupRequired] = useState(false);

  const t = useT(language);

  // Map the currency code to its symbol for convenient use in components
  const currencySymbol = CURRENCY_SYMBOLS[currency] || currency;

  // Apply light/dark mode to document root
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Apply colour theme to document root
  useEffect(() => {
    document.documentElement.setAttribute('data-colour-theme', colourTheme);
  }, [colourTheme]);

  useEffect(() => {
    document.documentElement.setAttribute('data-background', background);
  }, [background]);

  useEffect(() => {
    const token = localStorage.getItem('knitting_token');
    const headers = token ? { 'X-Session-Token': token } : {};
    fetch('/api/setup/status', { credentials: 'include' })
      .then(r => r.ok ? r.json() : { setup_required: false })
      .then(status => {
        if (status.setup_required) {
          setSetupRequired(true);
          return undefined;
        }
        return fetch('/api/auth/me', { headers, credentials: 'include' })
          .then(r => r.ok ? r.json() : null);
      })
      .then(userData => {
        if (userData === undefined) return;
        if (userData) {
          setUser(userData);
          setTheme(userData.theme || 'light');
          setColourTheme(userData.colour_theme || 'terracotta');
          setBackground(normalizeBackground(userData.background || 'default'));
          setLanguage(userData.language || 'en');
          setCurrency(userData.currency || 'NOK');
        } else {
          localStorage.removeItem('knitting_token');
        }
      })
      .catch(() => localStorage.removeItem('knitting_token'))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback((userData, token) => {
    localStorage.removeItem('knitting_token');
    setSetupRequired(false);
    setUser(userData);
    setTheme(userData.theme || 'light');
    setColourTheme(userData.colour_theme || 'terracotta');
    setBackground(normalizeBackground(userData.background || 'default'));
    setLanguage(userData.language || 'en');
    setCurrency(userData.currency || 'NOK');
  }, []);

  const logout = useCallback(async () => {
    const token = localStorage.getItem('knitting_token');
    const csrf = document.cookie.split('; ').find(row => row.startsWith('knitting_csrf='))?.split('=')[1] || '';
    const headers = {};
    if (token) headers['X-Session-Token'] = token;
    if (csrf) headers['X-CSRF-Token'] = decodeURIComponent(csrf);
    await fetch('/api/auth/logout', { method: 'POST', headers, credentials: 'include' }).catch(() => {});
    localStorage.removeItem('knitting_token');
    setUser(null);
    setTheme('light');
    setColourTheme('terracotta');
    setBackground('default');
    setLanguage('en');
    setCurrency('NOK');
  }, []);

  const updateSettings = useCallback(async (newTheme, newLanguage, newCurrency, newColourTheme, newBackground) => {
    const token = localStorage.getItem('knitting_token');
    const csrf = document.cookie.split('; ').find(row => row.startsWith('knitting_csrf='))?.split('=')[1] || '';
    // Use current values as fallback if not provided
    const ct = newColourTheme || colourTheme;
    const bg = normalizeBackground(newBackground || background);
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['X-Session-Token'] = token;
      if (csrf) headers['X-CSRF-Token'] = decodeURIComponent(csrf);
      await fetch('/api/auth/settings', {
        method: 'PUT',
        headers,
        credentials: 'include',
        body: JSON.stringify({ theme: newTheme, language: newLanguage, currency: newCurrency, colour_theme: ct, background: bg })
      });
      setTheme(newTheme);
      setLanguage(newLanguage);
      setCurrency(newCurrency);
      setColourTheme(ct);
      setBackground(bg);
      setUser(u => ({ ...u, theme: newTheme, language: newLanguage, currency: newCurrency, colour_theme: ct, background: bg }));
    } catch (e) {
      console.error('Failed to save settings', e);
    }
  }, [background, colourTheme]);

  return (
    <AppContext.Provider value={{
      user, theme, colourTheme, background, language, currency, currencySymbol, t,
      loading, setupRequired, login, logout, updateSettings
    }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
