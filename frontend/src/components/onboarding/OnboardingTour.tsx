import { useEffect, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import clsx from 'clsx';
import { X, ChevronRight, ChevronLeft, Sparkles } from 'lucide-react';
import type { ViewKey } from '@/components/shell/Sidebar';

type Step = {
  /** CSS selector to highlight (optional — if unset, shows as a centered modal) */
  target?: string;
  /** Switch to this view before showing the step */
  view?: ViewKey;
  title: string;
  body: string;
  /** Where to place the popover relative to the target. */
  placement?: 'top' | 'bottom' | 'left' | 'right' | 'center';
};

const STEPS: Step[] = [
  {
    title: 'Welcome to PULSE',
    body:
      "I'm a Bloomberg-style energy intelligence terminal — every panel is grounded in your OilMacroTrading curriculum and live free data feeds. I'll give you a 60-second tour. Press → to advance, Esc to skip.",
    placement: 'center',
  },
  {
    target: 'header',
    title: 'Live ticker tape',
    body:
      'Top bar polls Brent / WTI / NatGas / DXY / VIX / S&P / 10Y every 15s from yfinance, plus three trading-session clocks and a market-status chip.',
    placement: 'bottom',
  },
  {
    target: 'nav',
    title: 'Six workspaces',
    body:
      'Each tab is a different angle on the market: Desk (the landing view), Charts, Markets, Paper Trading, Regime, and the Signal Log. Press 1–6 anywhere to jump.',
    placement: 'right',
  },
  {
    view: 'desk',
    title: 'Signal Drill on the Desk',
    body:
      'The Desk lists weighted indicators across Brent, WTI, and NatGas. Click any indicator row to open a curriculum-grade reference modal. Score ranges −2 (strong sell) to +2 (strong buy).',
    placement: 'center',
  },
  {
    view: 'desk',
    title: 'Price Decomposition Waterfall',
    body:
      "Brent broken into its components: cost-of-carry FV, inventory adjustment, OPEC compliance, DXY, geo premium, curve momentum, macro residual. The closer 'modelled' is to 'actual', the better the model fits today.",
    placement: 'center',
  },
  {
    view: 'markets',
    target: 'details[data-section="inventories"]',
    title: 'EIA Surprise Tracker',
    body:
      'Inside MARKETS → Inventories. Wednesday 10:30 EST is the single most market-moving regular release in oil (curriculum Ch6). Live countdown + last 15 releases + surprise→price reaction regression.',
    placement: 'bottom',
  },
  {
    view: 'regime',
    title: 'Historical analogs',
    body:
      "Click the top regime pick to open the drill modal. The 'Historical analogs' section shows the closest past days by feature vector and what the spread did over the next 20 trading days — a sanity check on today's signal.",
    placement: 'center',
  },
  {
    title: 'Ask PULSE — anytime',
    body:
      "Bottom-right gold button (or just press '/') opens a chat dock. It does retrieval over the curriculum + your live market snapshot, then asks llama3 (if you have Ollama running). Ask anything: 'why is Brent up today?', 'explain backwardation', 'how should I read this curve?'",
    placement: 'center',
  },
];

const STORAGE_KEY = 'pulse.onboarding.seen.v2';

function getTargetRect(selector: string): DOMRect | null {
  const el = document.querySelector(selector);
  return el ? el.getBoundingClientRect() : null;
}

export function OnboardingTour({ onNavigate }: { onNavigate: (v: ViewKey) => void }) {
  const [visible, setVisible] = useState<boolean>(false);
  const [step, setStep] = useState<number>(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  // First-visit auto-open
  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) {
        setVisible(true);
      }
    } catch { /* localStorage disabled */ }
  }, []);

  // Esc to skip; arrows to navigate
  useEffect(() => {
    if (!visible) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
      else if (e.key === 'ArrowRight') next();
      else if (e.key === 'ArrowLeft') prev();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, step]);

  // When step changes, switch view if needed and re-measure target
  useEffect(() => {
    if (!visible) return;
    const s = STEPS[step];
    if (s.view) onNavigate(s.view);
    // Delay so the new view mounts before we measure
    const t = setTimeout(() => {
      if (s.target) setRect(getTargetRect(s.target));
      else setRect(null);
    }, 350);
    return () => clearTimeout(t);
  }, [step, visible, onNavigate]);

  // Re-measure on window resize/scroll
  useEffect(() => {
    if (!visible) return;
    const s = STEPS[step];
    if (!s.target) return;
    const reflow = () => setRect(getTargetRect(s.target!));
    window.addEventListener('resize', reflow);
    window.addEventListener('scroll', reflow, true);
    return () => {
      window.removeEventListener('resize', reflow);
      window.removeEventListener('scroll', reflow, true);
    };
  }, [step, visible]);

  const close = useCallback(() => {
    setVisible(false);
    try { localStorage.setItem(STORAGE_KEY, '1'); } catch { /* ignore */ }
  }, []);
  const next = useCallback(() => {
    setStep(s => Math.min(STEPS.length - 1, s + 1));
  }, []);
  const prev = useCallback(() => {
    setStep(s => Math.max(0, s - 1));
  }, []);

  if (!visible) return null;

  const cur = STEPS[step];
  const isLast = step === STEPS.length - 1;
  const isCenter = !cur.target || cur.placement === 'center';

  // Compute popover position
  let popStyle: React.CSSProperties = {};
  if (isCenter || !rect) {
    popStyle = { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' };
  } else {
    const placement = cur.placement ?? 'bottom';
    const margin = 16;
    const popWidth = 360;
    if (placement === 'bottom') {
      popStyle = {
        left: Math.max(margin, Math.min(window.innerWidth - popWidth - margin, rect.left)),
        top: rect.bottom + margin,
      };
    } else if (placement === 'top') {
      popStyle = {
        left: Math.max(margin, Math.min(window.innerWidth - popWidth - margin, rect.left)),
        bottom: window.innerHeight - rect.top + margin,
      };
    } else if (placement === 'right') {
      popStyle = {
        left: rect.right + margin,
        top: Math.max(margin, rect.top),
      };
    } else if (placement === 'left') {
      popStyle = {
        right: window.innerWidth - rect.left + margin,
        top: Math.max(margin, rect.top),
      };
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-[200] pointer-events-none">
      {/* Dim overlay with cutout */}
      <div className="absolute inset-0 bg-bg/80 backdrop-blur-sm pointer-events-auto" onClick={close}>
        {rect && !isCenter && (
          <div
            className="absolute pointer-events-none rounded-lg ring-2 ring-gold animate-pulse"
            style={{
              left: rect.left - 6,
              top: rect.top - 6,
              width: rect.width + 12,
              height: rect.height + 12,
              boxShadow: '0 0 0 9999px rgba(7,11,20,0.78), 0 0 40px rgba(212,175,55,0.6)',
            }}
          />
        )}
      </div>

      {/* Popover */}
      <div
        className={clsx(
          'absolute pointer-events-auto w-[360px] max-w-[calc(100vw-32px)]',
          'bg-bg-surface border border-border rounded-lg shadow-2xl p-5 animate-fade-in',
        )}
        style={popStyle}
      >
        {/* gold top stripe */}
        <div
          aria-hidden
          className="absolute inset-x-3 top-0 h-px pointer-events-none"
          style={{ background: 'linear-gradient(90deg, transparent, rgba(212,175,55,0.6), transparent)' }}
        />
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-gold" />
            <span className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">
              Step {step + 1} of {STEPS.length}
            </span>
          </div>
          <button
            onClick={close}
            className="p-1 rounded text-text-tertiary hover:text-text-primary hover:bg-bg-hover"
            aria-label="Skip tour"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <h3 className="font-display font-bold tracking-wider text-lg uppercase text-text-primary mb-2">
          {cur.title}
        </h3>
        <p className="text-[12.5px] text-text-secondary leading-relaxed mb-4">
          {cur.body}
        </p>

        {/* Progress dots */}
        <div className="flex items-center gap-1.5 mb-4">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={clsx(
                'h-1 rounded-full transition-all',
                i === step ? 'w-6 bg-gold' :
                i < step ? 'w-4 bg-gold/40' :
                'w-2 bg-border',
              )}
            />
          ))}
        </div>

        <div className="flex items-center justify-between gap-2">
          <button
            onClick={close}
            className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary hover:text-text-primary px-2 py-1.5"
          >
            Skip tour
          </button>
          <div className="flex gap-2">
            <button
              onClick={prev}
              disabled={step === 0}
              className="flex items-center gap-1 px-3 py-1.5 text-[11px] font-mono uppercase tracking-widest border border-border rounded text-text-secondary hover:text-text-primary hover:border-border-strong disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-3 h-3" />
              Back
            </button>
            {isLast ? (
              <button
                onClick={close}
                className="flex items-center gap-1 px-4 py-1.5 text-[11px] font-mono uppercase tracking-widest bg-gold text-bg hover:bg-gold-bright rounded font-semibold"
              >
                Get started
                <Sparkles className="w-3 h-3" />
              </button>
            ) : (
              <button
                onClick={next}
                className="flex items-center gap-1 px-4 py-1.5 text-[11px] font-mono uppercase tracking-widest bg-gold text-bg hover:bg-gold-bright rounded font-semibold"
              >
                Next
                <ChevronRight className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** Manually restart the tour from anywhere (e.g. a settings/help button). */
export function resetOnboarding() {
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  window.location.reload();
}
