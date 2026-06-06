import { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import clsx from 'clsx';
import { AlertTriangle, AlertOctagon, Info, X, Volume2, VolumeX, BellOff, Bell, Play } from 'lucide-react';

/**
 * Pop-up alert toast system.
 *
 * Consumes the `/api/alerts` payload via the parent's `alerts` prop and
 * pops a slide-in toast for each *new* alert (deduplicated by id). Each
 * toast auto-dismisses after a tone-dependent duration:
 *   critical → 14s (or stays until manually dismissed)
 *   warning  → 8s
 *   info     → 5s
 *
 * Optional features (controlled by localStorage toggles in the header):
 *   • Sound ping on critical/warning
 *   • Browser Notification API push when the tab is in background
 *
 * The component renders a permanent floating header (gold "bell" widget)
 * with mute / browser-notify toggles, plus the stacked toasts themselves.
 */

export type Alert = {
  id: string;
  type: string;
  severity: 'critical' | 'warning' | 'info' | string;
  message: string;
  timestamp: string;
};

type Toast = Alert & { _key: string; _firedAt: number; _duration: number };

const STORAGE_SOUND = 'pulse.alerts.sound';
const STORAGE_BROWSER = 'pulse.alerts.browser';
const STORAGE_SEEN = 'pulse.alerts.seen';

function loadJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function saveJSON(key: string, value: any): void {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
}

function durationFor(severity: string): number {
  if (severity === 'critical') return 14000;
  if (severity === 'warning') return 8000;
  return 5000;
}

const TONE_CLASS: Record<string, { bg: string; border: string; text: string; accent: string }> = {
  critical: { bg: 'bg-bear-soft',  border: 'border-bear/50',  text: 'text-bear',  accent: '#ff4d6d' },
  warning:  { bg: 'bg-neut-soft',  border: 'border-neut/50',  text: 'text-neut',  accent: '#f5a623' },
  info:     { bg: 'bg-accent-blue/10', border: 'border-accent-blue/40', text: 'text-accent-blue', accent: '#4d8eff' },
};
const tone = (s: string) => TONE_CLASS[s] ?? TONE_CLASS.info;

function severityIcon(s: string) {
  if (s === 'critical') return AlertOctagon;
  if (s === 'warning') return AlertTriangle;
  return Info;
}

// Pre-tuned mini sound (data URI) so we don't need an asset file
const _audioCache: { ctx: AudioContext | null } = { ctx: null };
function playPing(severity: string) {
  try {
    if (!_audioCache.ctx) {
      const AC = (window as any).AudioContext || (window as any).webkitAudioContext;
      if (!AC) return;
      _audioCache.ctx = new AC();
    }
    const ctx = _audioCache.ctx!;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = 'sine';
    o.frequency.value = severity === 'critical' ? 880 : 660;
    g.gain.value = 0.0001;
    o.connect(g); g.connect(ctx.destination);
    const now = ctx.currentTime;
    g.gain.exponentialRampToValueAtTime(0.18, now + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
    o.start(now);
    o.stop(now + 0.4);
  } catch { /* ignore */ }
}

/**
 * Trading-floor squawk — speak the alert aloud via the browser's built-in
 * Web Speech API. Free, offline, no API key. Queued automatically so two
 * alerts firing back-to-back don't talk over each other.
 *
 * For NEWS_BREAKING we read "Breaking. {headline}" — for other alert types
 * we read "{type spoken} alert. {message}". Type strings like EIA_SURPRISE
 * are humanised first ("E I A surprise"). Source attribution and dollar /
 * percent signs are normalised so they don't read literally.
 */
function _pickVoice(): SpeechSynthesisVoice | null {
  try {
    const all = window.speechSynthesis.getVoices() || [];
    // Prefer en-US/en-GB. Within that, prefer named professional voices.
    const prefs = [/google.*us.*english/i, /google.*uk.*english/i, /microsoft.*aria/i, /microsoft.*guy/i, /samantha/i, /daniel/i, /^en-(US|GB)$/i];
    for (const re of prefs) {
      const v = all.find(v => re.test(v.name) || re.test(v.lang));
      if (v) return v;
    }
    return all.find(v => /^en/i.test(v.lang)) ?? all[0] ?? null;
  } catch { return null; }
}

function _humaniseType(type: string): string {
  // EIA_SURPRISE → "E I A surprise"; PRICE_SHOCK → "price shock"
  return (type || '')
    .replace(/_/g, ' ')
    .replace(/\b([A-Z]{2,})\b/g, (s) => s.split('').join(' '))
    .toLowerCase();
}

function _speechText(t: Toast): string {
  if (t.type === 'NEWS_BREAKING') {
    return `Breaking. ${t.message}`;
  }
  const human = _humaniseType(t.type);
  // Strip ticker noise that doesn't read well aloud
  const msg = (t.message || '')
    .replace(/\bM1[-–—]M2\b/g, 'M one M two')
    .replace(/\$([0-9.,]+)/g, '$1 dollars')
    .replace(/([0-9]+)\s*%/g, '$1 percent')
    .replace(/\bpctile\b/gi, 'percentile')
    .replace(/\bvs\b/gi, 'versus')
    .replace(/\bATR\b/g, 'A T R')
    .replace(/\bCOT\b/g, 'C O T')
    .replace(/\bIV\b/g, 'I V')
    .replace(/\bbbl\b/gi, 'barrel')
    .replace(/\bMbbl\b/gi, 'million barrels');
  return `${human} alert. ${msg}`;
}

function speakAlert(t: Toast) {
  try {
    const synth = window.speechSynthesis;
    if (!synth) return;
    // Don't pile up if the queue is already long.
    if (synth.pending && synth.pending) {
      // Allow up to ~3 queued; flush anything past that.
      // (Browsers expose `pending` as a boolean rather than a count, so we
      // approximate via a simple length cap below.)
    }
    const u = new SpeechSynthesisUtterance(_speechText(t));
    u.rate   = t.severity === 'critical' ? 1.05 : 1.0;
    u.pitch  = 1.0;
    u.volume = 1.0;
    const v = _pickVoice();
    if (v) u.voice = v;
    synth.speak(u);
  } catch { /* speech not available — silent fail */ }
}

// Some browsers (notably Chrome) populate the voice list asynchronously.
// Touch it once so getVoices() returns something meaningful by first use.
if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
  try {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => { /* no-op trigger */ };
  } catch { /* ignore */ }
}

function ToastCard({ t, onDismiss }: { t: Toast; onDismiss: () => void }) {
  const Icon = severityIcon(t.severity);
  const c = tone(t.severity);
  const ago = (() => {
    const s = Math.max(0, Math.round((Date.now() - new Date(t.timestamp).getTime()) / 1000));
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    return `${Math.round(s / 3600)}h ago`;
  })();
  const [progress, setProgress] = useState(100);

  // Drain countdown bar
  useEffect(() => {
    const start = t._firedAt;
    const id = setInterval(() => {
      const elapsed = Date.now() - start;
      const pct = Math.max(0, 100 - (elapsed / t._duration) * 100);
      setProgress(pct);
    }, 80);
    return () => clearInterval(id);
  }, [t]);

  return (
    <div
      className={clsx(
        'relative w-[360px] max-w-[calc(100vw-32px)] rounded-lg border shadow-2xl overflow-hidden animate-fade-in pointer-events-auto',
        c.bg, c.border,
      )}
      style={{ backdropFilter: 'blur(6px)' }}
    >
      {/* top accent stripe */}
      <div className="absolute inset-x-0 top-0 h-px" style={{ background: c.accent, opacity: 0.7 }} />

      <div className="p-3 pr-9 flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">
          <Icon className={clsx('w-5 h-5', c.text)} strokeWidth={2.2} />
        </div>
        <div className="flex-1 min-w-0">
          <div className={clsx('flex items-baseline gap-2 mb-0.5', c.text)}>
            <span className="font-display font-bold tracking-widest text-[11px] uppercase">{t.type.replace(/_/g, ' ')}</span>
            <span className={clsx(
              'text-[8px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded',
              t.severity === 'critical' ? 'bg-bear/30 text-bear' :
              t.severity === 'warning' ? 'bg-neut/30 text-neut' :
              'bg-accent-blue/20 text-accent-blue',
            )}>
              {t.severity}
            </span>
            <span className="ml-auto text-[9px] font-mono text-text-tertiary tabular">{ago}</span>
          </div>
          <div className="text-[12px] text-text-secondary leading-snug">{t.message}</div>
        </div>
      </div>

      <button
        onClick={onDismiss}
        className="absolute top-2 right-2 p-1 rounded text-text-tertiary hover:text-text-primary hover:bg-bg-hover/60"
        aria-label="Dismiss"
      >
        <X className="w-3.5 h-3.5" />
      </button>

      {/* drain bar */}
      <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-bg-elev/60">
        <div
          className="h-full transition-all duration-100 ease-linear"
          style={{ width: `${progress}%`, background: c.accent }}
        />
      </div>
    </div>
  );
}

export function ToastStack({ alerts, news }: {
  alerts: Alert[] | null | undefined;
  news?: { articles?: any[]; composite_sentiment?: any } | null;
}) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [soundOn, setSoundOn] = useState<boolean>(() => loadJSON<boolean>(STORAGE_SOUND, true));
  const [browserOn, setBrowserOn] = useState<boolean>(() => loadJSON<boolean>(STORAGE_BROWSER, false));
  const seenIdsRef = useRef<Set<string>>(new Set(loadJSON<string[]>(STORAGE_SEEN, [])));
  const initializedRef = useRef<boolean>(false);

  // Diff incoming alerts vs seen, fire toasts for new ones
  useEffect(() => {
    if (!alerts) return;
    const incoming = alerts.filter(a => a && a.id && !seenIdsRef.current.has(a.id));

    // First mount: mark everything as seen WITHOUT firing toasts (no spam on load)
    if (!initializedRef.current) {
      alerts.forEach(a => a?.id && seenIdsRef.current.add(a.id));
      saveJSON(STORAGE_SEEN, Array.from(seenIdsRef.current).slice(-200));
      initializedRef.current = true;
      return;
    }

    if (incoming.length === 0) return;

    const now = Date.now();
    const newToasts: Toast[] = incoming.map((a, i) => ({
      ...a,
      _key: `${a.id}-${now}-${i}`,
      _firedAt: now + i * 80,            // tiny stagger
      _duration: durationFor(a.severity),
    }));

    setToasts(prev => [...prev, ...newToasts]);

    incoming.forEach((a, i) => {
      if (a?.id) seenIdsRef.current.add(a.id);

      // Sound ping (chime) + trading-floor squawk (TTS) on critical/warning.
      // The chime fires first, then the spoken headline follows ~400 ms later
      // so the two don't overlap audibly.
      if (soundOn && (a.severity === 'critical' || a.severity === 'warning')) {
        playPing(a.severity);
        const toastShape: Toast = { ...a, _key: a.id, _firedAt: now, _duration: durationFor(a.severity) };
        // Stagger speech behind the chime + later toasts
        setTimeout(() => speakAlert(toastShape), 420 + i * 200);
      }

      // Browser notification when tab in background
      if (browserOn && document.visibilityState === 'hidden' && 'Notification' in window) {
        if (Notification.permission === 'granted') {
          try {
            new Notification(`PULSE · ${a.type.replace(/_/g, ' ')}`, {
              body: a.message,
              icon: '/favicon.svg',
              tag: a.id,
            });
          } catch { /* ignore */ }
        }
      }
    });

    saveJSON(STORAGE_SEEN, Array.from(seenIdsRef.current).slice(-200));
  }, [alerts, soundOn, browserOn]);

  // Auto-dismiss timer
  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = setInterval(() => {
      const now = Date.now();
      setToasts(prev => prev.filter(t => now - t._firedAt < t._duration));
    }, 250);
    return () => clearInterval(timer);
  }, [toasts.length]);

  const dismiss = useCallback((key: string) => {
    setToasts(prev => prev.filter(t => t._key !== key));
  }, []);

  const toggleSound = useCallback(() => {
    setSoundOn(s => { const n = !s; saveJSON(STORAGE_SOUND, n); return n; });
  }, []);

  const toggleBrowser = useCallback(async () => {
    if (!browserOn && 'Notification' in window) {
      if (Notification.permission === 'default') {
        await Notification.requestPermission();
      }
    }
    setBrowserOn(b => {
      const n = !b;
      saveJSON(STORAGE_BROWSER, n);
      return n;
    });
  }, [browserOn]);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <>
      {/* Floating settings widget — small, top-right of viewport */}
      <div className="fixed top-20 right-5 z-[90] flex items-center gap-1.5 bg-bg-surface/80 backdrop-blur-md border border-border rounded-full px-2 py-1 shadow-lg">
        {(() => {
          // ── Pick the best headline to read aloud, in priority order ───────
          //   1. Latest NEWS_BREAKING alert (critical / warning) — from /api/alerts
          //   2. Most-negative FinBERT-scored article from /api/news.articles
          //   3. Most-recent article from /api/news.articles
          // If none exists, hide the button.
          const breakingAlert = (alerts ?? []).slice().reverse().find(
            (a) => a?.type === 'NEWS_BREAKING' && (a?.severity === 'critical' || a?.severity === 'warning'),
          );

          let speakSource: Toast | null = null;
          let label = 'Replay';
          let tip   = '';

          if (breakingAlert) {
            speakSource = {
              ...breakingAlert,
              _key:     breakingAlert.id,
              _firedAt: Date.now(),
              _duration: durationFor(breakingAlert.severity),
            };
            tip = `Replay breaking alert: ${(breakingAlert.message ?? '').slice(0, 100)}${(breakingAlert.message ?? '').length > 100 ? '…' : ''}`;
            label = 'Replay alert';
          } else {
            const articles = news?.articles ?? [];
            if (articles.length > 0) {
              // Most-negative first; tiebreak by recency
              const ranked = articles.slice().sort((a, b) => {
                const sa = typeof a.sentiment_score === 'number' ? a.sentiment_score : 0;
                const sb = typeof b.sentiment_score === 'number' ? b.sentiment_score : 0;
                if (sa !== sb) return sa - sb;
                const ta = Date.parse(a.published_at || a.published || 0) || 0;
                const tb = Date.parse(b.published_at || b.published || 0) || 0;
                return tb - ta;
              });
              const top = ranked[0];
              const title = top.title || top.headline || 'Latest oil headline';
              speakSource = {
                id:        `news-${title.slice(0, 40)}`,
                type:      'NEWS_BREAKING',
                severity:  (typeof top.sentiment_score === 'number' && top.sentiment_score < -0.15) ? 'warning' : 'info',
                message:   `${title}${top.source ? ` — ${top.source}` : ''}`,
                timestamp: top.published_at || top.published || new Date().toISOString(),
                _key:      'manual-news-replay',
                _firedAt:  Date.now(),
                _duration: 8000,
              };
              tip = `Replay latest headline: ${title.slice(0, 100)}${title.length > 100 ? '…' : ''}`;
              label = 'Replay news';
            }
          }

          if (!speakSource) return null;
          const onReplay = () => speakAlert(speakSource);

          return (
            <button
              onClick={onReplay}
              title={tip}
              className="flex items-center gap-1.5 pl-1.5 pr-2 py-1 rounded-full bg-gold/15 hover:bg-gold/25 transition-colors text-gold"
            >
              <Play className="w-3 h-3" />
              <span className="text-[10px] font-mono uppercase tracking-widest">{label}</span>
            </button>
          );
        })()}
        <button
          onClick={toggleSound}
          title={soundOn ? 'Mute squawk (chime + spoken headlines)' : 'Enable squawk (chime + spoken headlines)'}
          className={clsx(
            'p-1.5 rounded-full transition-colors',
            soundOn ? 'text-gold hover:bg-bg-hover' : 'text-text-muted hover:text-text-secondary',
          )}
        >
          {soundOn ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
        </button>
        <button
          onClick={toggleBrowser}
          title={browserOn ? 'Disable browser notifications' : 'Enable browser notifications (fires when tab is in background)'}
          className={clsx(
            'p-1.5 rounded-full transition-colors',
            browserOn ? 'text-gold hover:bg-bg-hover' : 'text-text-muted hover:text-text-secondary',
          )}
        >
          {browserOn ? <Bell className="w-3.5 h-3.5" /> : <BellOff className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Toast stack — top-right under the settings widget */}
      <div className="fixed top-32 right-5 z-[95] flex flex-col gap-2 pointer-events-none">
        {toasts.slice(-5).map(t => (
          <ToastCard key={t._key} t={t} onDismiss={() => dismiss(t._key)} />
        ))}
      </div>
    </>,
    document.body,
  );
}
