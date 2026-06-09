import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
import { initObservability } from './lib/observability';

// Sprint 0b — initialise Sentry before any component renders so errors
// during the first paint are captured. No-op when VITE_SENTRY_DSN is unset.
initObservability();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
