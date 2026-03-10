/**
 * AppContext.js
 * Global state that every component in the app can read.
 * Stores: logged-in user, theme (light/dark), language (en/no), currency (NOK/USD/GBP)
 *
 * Usage in any component:
 *   const { user, theme, language, currency, currencySymbol, t, login, logout } = useApp();
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useT } from './translations';

const AppContext = createContext(null);

// Map currency code → symbol
export const CURRENCY_SYMBOLS = { NOK: 'kr', USD: '$', GBP: '£' };
export const CURRENCIES = [
  { code: 'NOK', label: 'kr — Norwegian Krone' },
  { code: 'USD', label: '$ — US Dollar' },
  { code: 'GBP', label: '£ — British Pound' },
];

export function AppProvider({ children }) {
  const [user, setUser]               = useState(null);
  const [theme, setTheme]             = useState('light');
  const [colourTheme, setColourTheme] = useState('terracotta');
  const [language, setLanguage]       = useState('en');
  const [currency, setCurrency]       = useState('NOK');
  const [loading, setLoading]         = useState(true);

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
    const token = localStorage.getItem('knitting_token');
    if (!token) { setLoading(false); return; }
    fetch('/api/auth/me', { headers: { 'X-Session-Token': token } })
      .then(r => r.ok ? r.json() : null)
      .then(userData => {
        if (userData) {
          setUser(userData);
          setTheme(userData.theme || 'light');
          setColourTheme(userData.colour_theme || 'terracotta');
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
    localStorage.setItem('knitting_token', token);
    setUser(userData);
    setTheme(userData.theme || 'light');
    setColourTheme(userData.colour_theme || 'terracotta');
    setLanguage(userData.language || 'en');
    setCurrency(userData.currency || 'NOK');
  }, []);

  const logout = useCallback(async () => {
    const token = localStorage.getItem('knitting_token');
    if (token) {
      await fetch('/api/auth/logout', {
        method: 'POST', headers: { 'X-Session-Token': token }
      }).catch(() => {});
    }
    localStorage.removeItem('knitting_token');
    setUser(null);
    setTheme('light');
    setColourTheme('terracotta');
    setLanguage('en');
    setCurrency('NOK');
  }, []);

  const updateSettings = useCallback(async (newTheme, newLanguage, newCurrency, newColourTheme) => {
    const token = localStorage.getItem('knitting_token');
    // Use current values as fallback if not provided
    const ct = newColourTheme || colourTheme;
    try {
      await fetch('/api/auth/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-Session-Token': token },
        body: JSON.stringify({ theme: newTheme, language: newLanguage, currency: newCurrency, colour_theme: ct })
      });
      setTheme(newTheme);
      setLanguage(newLanguage);
      setCurrency(newCurrency);
      setColourTheme(ct);
      setUser(u => ({ ...u, theme: newTheme, language: newLanguage, currency: newCurrency, colour_theme: ct }));
    } catch (e) {
      console.error('Failed to save settings', e);
    }
  }, [colourTheme]);

  return (
    <AppContext.Provider value={{
      user, theme, colourTheme, language, currency, currencySymbol, t,
      loading, login, logout, updateSettings
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
