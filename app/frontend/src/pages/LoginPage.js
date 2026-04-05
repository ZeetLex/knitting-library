/**
 * LoginPage.js
 * Step 1: username + password.
 * Step 2 (if 2FA enabled): 6-digit TOTP code.
 */

import React, { useState, useRef, useEffect } from 'react';
import { useApp } from '../utils/AppContext';
import { verify2FAChallenge } from '../utils/api';
import './LoginPage.css';

export default function LoginPage() {
  const { login } = useApp();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  // 2FA challenge state
  const [challenge, setChallenge] = useState(null); // token string when 2FA needed
  const [totpCode, setTotpCode]   = useState('');
  const totpRef = useRef(null);

  useEffect(() => {
    if (challenge && totpRef.current) totpRef.current.focus();
  }, [challenge]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) return;
    setError('');
    setLoading(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        setError('Incorrect username or password');
        setLoading(false);
        return;
      }
      const data = await res.json();
      if (data.needs_2fa) {
        setChallenge(data.challenge_token);
        setLoading(false);
        return;
      }
      login(data.user, data.token);
    } catch {
      setError('Could not connect to the server. Is it running?');
      setLoading(false);
    }
  };

  const handleTOTP = async (e) => {
    e.preventDefault();
    if (totpCode.length !== 6) return;
    setError('');
    setLoading(true);
    try {
      const data = await verify2FAChallenge(challenge, totpCode);
      login(data.user, data.token);
    } catch (err) {
      setError(err.message || 'Invalid code');
      setTotpCode('');
      setLoading(false);
    }
  };

  // ── 2FA step ───────────────────────────────────────────────────────────────
  if (challenge) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="login-logo">
            <span className="login-logo-icon">🧶</span>
            <h1 className="login-app-name">Knitting Library</h1>
          </div>
          <p className="login-subtitle">Two-factor authentication</p>
          <p className="login-2fa-hint">
            Open your authenticator app and enter the 6-digit code.
          </p>
          <form className="login-form" onSubmit={handleTOTP}>
            <div className="login-field">
              <label htmlFor="totp">Authentication code</label>
              <input
                id="totp"
                ref={totpRef}
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                value={totpCode}
                onChange={e => setTotpCode(e.target.value.replace(/\D/g, ''))}
                placeholder="000000"
                autoComplete="one-time-code"
                disabled={loading}
                className="login-totp-input"
              />
            </div>
            {error && <p className="login-error">{error}</p>}
            <button
              type="submit"
              className="login-btn"
              disabled={loading || totpCode.length !== 6}
            >
              {loading ? 'Verifying…' : 'Verify'}
            </button>
            <button
              type="button"
              className="login-back-link"
              onClick={() => { setChallenge(null); setTotpCode(''); setError(''); }}
            >
              ← Back to login
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ── Password step ──────────────────────────────────────────────────────────
  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <span className="login-logo-icon">🧶</span>
          <h1 className="login-app-name">Knitting Library</h1>
        </div>
        <p className="login-subtitle">Sign in to your library</p>
        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="Enter your username"
              autoFocus
              autoComplete="username"
              disabled={loading}
            />
          </div>
          <div className="login-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Enter your password"
              autoComplete="current-password"
              disabled={loading}
            />
          </div>
          {error && <p className="login-error">{error}</p>}
          <button
            type="submit"
            className="login-btn"
            disabled={loading || !username || !password}
          >
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
