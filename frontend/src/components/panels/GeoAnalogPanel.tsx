import { useState, useCallback, useEffect } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { api } from '@/lib/api';

/**
 * Geo RAG analogs — type/paste a location-news headline, get the k closest
 * historical geo-events (interpretable nearest-neighbour over asset-type +
 * event-type + signed conviction) and a similarity-weighted per-node nowcast of
 * what each did to the price nodes. Backs onto /api/news/geo/analogs.
 */

interface NodeForecast {
  n_analogs: number; pred_dir: number; mean_move?: number;
  mean_vn?: number; analog_agree?: number; basis: string;
}
interface Analog {
  published_at: string; title: string | null; asset_type: string | null;
  event_type: string | null; regime: string | null; similarity: number;
}
interface Narration {
  available: boolean; source: string; note: string; horizon?: number;
}
interface AnalogResult {
  title: string; available: boolean; reason?: string;
  query?: { asset_type: string | null; event_type: string | null; conviction: Record<string, number> };
  horizon?: number; k?: number; n_matched?: number;
  nodes?: Record<string, NodeForecast>; analogs?: Analog[]; index_size?: number;
  narration?: Narration;
}

const EXAMPLES = [
  'Iran closes Strait of Hormuz to oil tankers after US strikes',
  'Drone strike sparks fire at a major Saudi refinery',
  'Hormuz reopens as ceasefire holds, crude tumbles',
];

const NODE_LABEL: Record<string, string> = {
  brent_flat: 'Brent flat', brent_structure: 'Brent M1-M12', wti_brent: 'WTI−Brent',
  ho_crack: 'ULSD crack', gasoil_crack: 'Gasoil crack', rbob_crack: 'RBOB crack', regrade: 'Regrade',
};

export function GeoAnalogPanel({ prefill }: { prefill?: string | null } = {}) {
  const [q, setQ] = useState('');
  const [res, setRes] = useState<AnalogResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = useCallback(async (title: string) => {
    const t = title.trim();
    if (!t) return;
    setLoading(true); setErr(null);
    try {
      const r = (await api.newsGeoAnalogs(t, 5, 5, true)) as AnalogResult;
      setRes(r);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Pre-fill from the geo map: a clicked asset hands us a headline → fill + run.
  useEffect(() => {
    const t = (prefill ?? '').trim();
    if (!t) return;
    setQ(t);
    run(t);
  }, [prefill, run]);

  return (
    <Panel title="Geo analogs · this event ≈ past events"
      subtitle="Nearest historical geo-events + what each did to the nodes (+5d)"
      accent="gold" source="geo_analogs" staticMount>
      <div className="flex gap-2 mb-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') run(q); }}
          placeholder="Paste a location-news headline…"
          className="flex-1 bg-bg-card/50 border border-border/50 rounded px-2 py-1.5 text-[11px] font-mono text-text-secondary focus:outline-none focus:border-gold/50"
        />
        <button onClick={() => run(q)} disabled={loading || !q.trim()}
          className="text-[10px] font-mono uppercase tracking-wide px-3 py-1.5 rounded border border-gold/40 text-gold-bright bg-gold/10 hover:bg-gold/20 disabled:opacity-40">
          {loading ? '…' : 'Find'}
        </button>
      </div>
      <div className="flex flex-wrap gap-1 mb-3">
        {EXAMPLES.map((ex) => (
          <button key={ex} onClick={() => { setQ(ex); run(ex); }}
            className="text-[9px] font-mono text-text-muted hover:text-text-secondary border border-border/40 rounded px-1.5 py-0.5 truncate max-w-[210px]"
            title={ex}>
            {ex}
          </button>
        ))}
      </div>

      {err && <div className="text-[11px] font-mono text-bear px-1 py-2">Analogs endpoint error: {err}</div>}

      {res && !res.available && (
        <div className="text-[11px] font-mono text-text-tertiary px-1 py-3">
          {res.reason ?? 'No geo asset/impact resolved for that headline.'}
        </div>
      )}

      {res?.available && (
        <div className="space-y-3">
          <div className="text-[10px] font-mono text-text-muted">
            <span className="text-text-tertiary uppercase tracking-wide">query</span>{' '}
            <span className="text-text-secondary">{res.query?.asset_type ?? '?'} · {res.query?.event_type ?? '?'}</span>
            {' '}· matched {res.n_matched ?? 0} of {res.index_size ?? '—'} indexed events
          </div>

          {/* LLM-narrated desk note — grounded ONLY in the retrieved analogs + graded edges */}
          {res.narration?.note && (
            <div className="rounded-md border border-gold/30 bg-gold/5 px-3 py-2">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[8.5px] font-mono uppercase tracking-widest text-gold-bright">Desk note</span>
                <span className="text-[8px] font-mono text-text-muted border border-border/40 rounded px-1 py-px"
                  title={res.narration.source === 'groq'
                    ? 'free-Groq narration grounded in the retrieved analogs + graded edges'
                    : res.narration.source === 'template'
                      ? 'deterministic note (no LLM key) — built from the same analog numbers'
                      : res.narration.source}>
                  {res.narration.source === 'groq' ? 'Groq' : res.narration.source === 'template' ? 'rule-based' : res.narration.source}
                </span>
              </div>
              <p className="text-[11px] font-mono text-text-secondary leading-relaxed">{res.narration.note}</p>
            </div>
          )}

          {/* per-node forecast from the analogs */}
          <div>
            <div className="grid grid-cols-[1fr_70px_64px_70px] gap-2 text-[9.5px] font-mono text-text-muted uppercase tracking-wide px-1 mb-1">
              <span>Node</span><span className="text-right">mean Δ5d</span><span className="text-right">agree</span><span className="text-right">n</span>
            </div>
            {Object.entries(res.nodes ?? {}).filter(([, f]) => f.basis === 'analog').map(([n, f]) => (
              <div key={n} className="grid grid-cols-[1fr_70px_64px_70px] gap-2 items-center text-[10.5px] font-mono tabular py-0.5 px-1">
                <span className="text-text-secondary truncate">{NODE_LABEL[n] ?? n}</span>
                <span className={clsx('text-right font-bold',
                  (f.mean_move ?? 0) > 0 ? 'text-bull' : (f.mean_move ?? 0) < 0 ? 'text-bear' : 'text-text-muted')}>
                  {f.mean_move == null ? '—' : `${f.mean_move > 0 ? '+' : ''}${f.mean_move.toFixed(2)}`}
                </span>
                <span className={clsx('text-right',
                  (f.analog_agree ?? 0) >= 0.6 ? 'text-bull' : (f.analog_agree ?? 0) <= 0.4 ? 'text-bear' : 'text-text-muted')}
                  title="weighted fraction of analogs that moved in the predicted direction">
                  {f.analog_agree == null ? '—' : `${(f.analog_agree * 100).toFixed(0)}%`}
                </span>
                <span className="text-right text-text-tertiary">{f.n_analogs}</span>
              </div>
            ))}
          </div>

          {/* nearest analogs */}
          <div>
            <div className="text-[9.5px] font-mono text-text-muted uppercase tracking-wide px-1 mb-1">Nearest analogs</div>
            <div className="space-y-0.5 max-h-[220px] overflow-y-auto">
              {(res.analogs ?? []).map((a, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px] font-mono py-0.5 px-1 rounded hover:bg-bg-card/30">
                  <span className="text-gold-bright font-bold w-9 text-right">{a.similarity.toFixed(2)}</span>
                  <span className="text-text-muted w-[120px] truncate">{a.asset_type}/{a.event_type}</span>
                  <span className="text-text-tertiary w-[68px]">{(a.published_at ?? '').slice(0, 10)}</span>
                  <span className="text-text-secondary flex-1 truncate" title={a.title ?? ''}>{a.title ?? '—'}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="text-[9.5px] font-mono text-text-muted leading-relaxed">
            Retrieval over the graded event panel; similarity = cosine over asset-type + event-type + signed
            conviction (an opposite event ranks low). Single-episode index — descriptive, not a fitted edge.
          </div>
        </div>
      )}
    </Panel>
  );
}
