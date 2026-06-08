import React, { useState } from 'react';
import { useApp } from '../utils/AppContext';
import { createFirstAdmin } from '../utils/api';
import './LoginPage.css';

export default function SetupPage() {
  const { login } = useApp();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!username.trim()) {
      setError('Username is required');
      return;
    }
    if (password.length < 12) {
      setError('Password must be at least 12 characters');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      const data = await createFirstAdmin(username.trim(), password);
      login(data.user, data.token);
    } catch (err) {
      setError(err.message || 'Setup failed');
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <span className="login-logo-icon">🧶</span>
          <h1 className="login-app-name">Knitting Library</h1>
        </div>
        <p className="login-subtitle">Create your first admin account</p>
        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-field">
            <label htmlFor="setup-username">Username</label>
            <input
              id="setup-username"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              disabled={loading}
              autoFocus
            />
          </div>
          <div className="login-field">
            <label htmlFor="setup-password">Password</label>
            <input
              id="setup-password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="new-password"
              disabled={loading}
            />
          </div>
          <div className="login-field">
            <label htmlFor="setup-confirm">Confirm password</label>
            <input
              id="setup-confirm"
              type="password"
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              autoComplete="new-password"
              disabled={loading}
            />
          </div>
          {error && <p className="login-error">{error}</p>}
          <button type="submit" className="login-btn" disabled={loading}>
            {loading ? 'Creating account...' : 'Create admin account'}
          </button>
        </form>
      </div>
    </div>
  );
}
