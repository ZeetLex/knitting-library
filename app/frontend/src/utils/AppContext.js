/**
 * AppContext.js
 * Global state that every component in the app can read.
 * Stores: logged-in user, theme (light/dark), language (en/no)
 *
 * Usage in any component:
 *   const { user, theme, language, t, login, logout } = useApp();
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useT } from './translations';

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [user, setUser]         = useState(null);       // null = not logged in
  const [theme, setTheme]       = useState('light');
  const [language, setLanguage] = useState('en');
  const [loading, setLoading]   = useState(true);       // true while checking session

  const t = useT(language);

  // Apply theme to the document root so CSS variables work globally
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // On first load, check if there's a saved session token
  useEffect(() => {
    const token = localStorage.getItem('knitting_token');
    if (!token) { setLoading(false); return; }

    fetch('/api/auth/me', {
      headers: { 'X-Session-Token': token }
    })
      .then(r => r.ok ? r.json() : null)
      .then(userData => {
        if (userData) {
          setUser(userData);
          setTheme(userData.theme || 'light');
          setLanguage(userData.language || 'en');
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
    setLanguage(userData.language || 'en');
  }, []);

  const logout = useCallback(async () => {
    const token = localStorage.getItem('knitting_token');
    if (token) {
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'X-Session-Token': token }
      }).catch(() => {});
    }
    localStorage.removeItem('knitting_token');
    setUser(null);
    setTheme('light');
    setLanguage('en');
  }, []);

  const updateSettings = useCallback(async (newTheme, newLanguage) => {
    const token = localStorage.getItem('knitting_token');
    try {
      await fetch('/api/auth/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-Session-Token': token },
        body: JSON.stringify({ theme: newTheme, language: newLanguage })
      });
      setTheme(newTheme);
      setLanguage(newLanguage);
      setUser(u => ({ ...u, theme: newTheme, language: newLanguage }));
    } catch (e) {
      console.error('Failed to save settings', e);
    }
  }, []);

  return (
    <AppContext.Provider value={{ user, theme, language, t, loading, login, logout, updateSettings }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
