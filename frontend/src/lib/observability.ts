/**
 * Frontend observability — Sentry init for React.
 *
 * Sprint 0b. Initialised once in main.tsx before <App /> mounts. No-op when
 * VITE_SENTRY_DSN is unset, so a developer without secrets can still run the
 * dashboard. The DSN is intentionally public per Sentry's design.
 *
 * Errors reach Sentry via three paths:
 *   1. window.onerror / unhandledrejection — captured automatically by the SDK
 *   2. React component errors — captured by the <SentryErrorBoundary> below
 *   3. Manual: `captureException(err, { tags: { … } })`
 */
import * as Sentry from '@sentry/react';

const DSN     = import.meta.env.VITE_SENTRY_DSN  as string | undefined;
const ENV     = (import.meta.env.VITE_SENTRY_ENV as string | undefined) || 'local';
const RELEASE = (import.meta.env.VITE_PULSE_RELEASE as string | undefined) || 'pulse@dev';

let initialised = false;

export function initObservability(): void {
  if (initialised) return;
  if (!DSN) {
    // eslint-disable-next-line no-console
    console.info('[observability] VITE_SENTRY_DSN not set — Sentry disabled');
    return;
  }
  try {
    Sentry.init({
      dsn: DSN,
      environment: ENV,
      release: RELEASE,
      // Lightweight: just errors. No performance traces, no replays — those
      // burn quota and we don't need them yet.
      tracesSampleRate: 0,
      // Don't ship request/response bodies; the DSN is the only thing we
      // need to expose.
      sendDefaultPii: false,
      initialScope: { tags: { component: 'pulse-frontend' } },
    });
    initialised = true;
  } catch (e) {
    // never let observability break the app
    // eslint-disable-next-line no-console
    console.warn('[observability] Sentry init failed', e);
  }
}

/** Manually report an exception with optional tags. */
export function captureException(err: unknown, tags?: Record<string, string>): void {
  if (!initialised) {
    // eslint-disable-next-line no-console
    console.warn('[observability] captureException (Sentry off):', err, tags);
    return;
  }
  Sentry.withScope((scope) => {
    if (tags) for (const [k, v] of Object.entries(tags)) scope.setTag(k, v);
    Sentry.captureException(err);
  });
}

/** Re-export the Sentry-aware ErrorBoundary so views can wrap risky subtrees. */
export const SentryErrorBoundary = Sentry.ErrorBoundary;
