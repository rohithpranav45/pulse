import { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import clsx from 'clsx';
import { AlertTriangle, AlertOctagon, Info, X, Volume2, VolumeX, BellOff, Bell } from 'lucide-react';

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

export function ToastStack({ alerts }: { alerts: Alert[] | null | undefined }) {
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

    incoming.forEach(a => {
      if (a?.id) seenIdsRef.current.add(a.id);

      // Sound ping
      if (soundOn && (a.severity === 'critical' || a.severity === 'warning')) {
        playPing(a.severity);
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
      <div className="fixed top-20 right-5 z-[90] flex gap-1.5 bg-bg-surface/80 backdrop-blur-md border border-border rounded-full px-2 py-1 shadow-lg">
        <button
          onClick={toggleSound}
          title={soundOn ? 'Mute alert sounds' : 'Enable alert sounds'}
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
