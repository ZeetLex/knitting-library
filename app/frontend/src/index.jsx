import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
// Self-hosted fonts via @fontsource — no Google CDN requests at runtime
import '@fontsource/playfair-display/400.css';
import '@fontsource/playfair-display/600.css';
import '@fontsource/playfair-display/700.css';
import '@fontsource/dm-sans/300.css';
import '@fontsource/dm-sans/400.css';
import '@fontsource/dm-sans/500.css';
import '@fontsource/dm-sans/600.css';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
