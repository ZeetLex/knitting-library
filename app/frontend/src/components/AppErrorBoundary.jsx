import { Component } from 'react';

// Catches any uncaught JS crash anywhere in the app and shows a recoverable
// screen instead of leaving the user on a black/blank tab with no way back in.
export default class AppErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error('App crashed:', error, info?.componentStack); }
  render() {
    if (this.state.error) {
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', padding: 32, textAlign: 'center' }}>
          <div style={{ maxWidth: 420 }}>
            <h2 style={{ marginBottom: 12 }}>Something went wrong</h2>
            <p style={{ marginBottom: 20, opacity: 0.8 }}>The app hit an unexpected error. Reloading usually fixes it.</p>
            <button
              style={{ padding: '10px 20px', cursor: 'pointer', borderRadius: 8, border: 'none', background: '#c4714a', color: '#fff', fontSize: 15 }}
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
