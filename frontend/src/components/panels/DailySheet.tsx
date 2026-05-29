/**
 * Daily Briefing Sheet — a print-optimized 1-page snapshot of PULSE.
 *
 * Rendered off-screen normally; appears full-screen when print media
 * is active (Ctrl/Cmd+P or our "Daily Sheet" button). Uses the same
 * live snapshot as the rest of the dashboard so what you print is
 * exactly what you see.
 */
import { fmt, signalLabel } from '@/lib/fmt';

const ASSETS = [
  { key: 'brent',     label: 'BRENT',   ticker: 'BZ=F' },
  { key: 'wti',       label: 'WTI',     ticker: 'CL=F' },
  { key: 'henry_hub', label: 'NAT GAS', ticker: 'NG=F' },
];

export function DailySheet({ all, tradeIdea }: { all: any; tradeIdea: any }) {
  const prices = all?.prices ?? {};
  const signal = all?.signal ?? {};
  const fv = all?.fair_value?.brent ?? {};
  const fund = all?.fundamentals ?? {};
  const curve = all?.curve ?? {};
  const cracks = (all?.cracks ?? {}).crack_spreads ?? {};
  const fcov = all?.forward_cover ?? {};

  const inv = fund?.inventory?.crude_stocks ?? {};
  const cot = fund?.cot?.crude_oil ?? {};
  const geo = fund?.geo_risk ?? {};

  const bc = curve?.brent?.contracts ?? [];
  const wc = curve?.wti?.contracts ?? [];
  const m1m2 = bc[0]?.price && bc[1]?.price ? bc[0].price - bc[1].price : null;
  const brtWti = bc[0]?.price && wc[0]?.price ? bc[0].price - wc[0].price : null;

  const now = new Date();

  return (
    <div id="daily-sheet" className="hidden print:block bg-white text-black p-8 font-sans">
      {/* HEADER */}
      <div className="border-b-2 border-black pb-3 mb-4 flex items-center justify-between">
        <div>
          <div className="text-3xl font-extrabold tracking-[0.3em]" style={{ color: '#b8941f' }}>PULSE</div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-gray-600">
            Energy Intelligence · Daily Briefing
          </div>
        </div>
        <div className="text-right">
          <div className="text-sm font-mono">
            {now.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          </div>
          <div className="text-[10px] font-mono text-gray-600">
            Generated {now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })} local
          </div>
        </div>
      </div>

      {/* PRICES */}
      <section className="mb-4">
        <h2 className="text-xs font-bold uppercase tracking-widest border-b border-gray-300 mb-2">Spot Prices</h2>
        <table className="w-full text-[12px] font-mono">
          <thead>
            <tr className="text-gray-600 text-[10px] uppercase">
              <th className="text-left py-1">Asset</th>
              <th className="text-right">Spot</th>
              <th className="text-right">Δ Day</th>
              <th className="text-right">Δ %</th>
              <th className="text-right">High</th>
              <th className="text-right">Low</th>
            </tr>
          </thead>
          <tbody>
            {ASSETS.map(a => {
              const p = prices[a.key] ?? {};
              return (
                <tr key={a.key} className="border-t border-gray-200">
                  <td className="py-1.5"><strong>{a.label}</strong> <span className="text-gray-500 text-[10px]">{a.ticker}</span></td>
                  <td className="text-right">${fmt.price(p.price)}</td>
                  <td className="text-right">{p.change_abs !== undefined ? fmt.signed(p.change_abs) : '—'}</td>
                  <td className="text-right" style={{ color: (p.change_pct ?? 0) >= 0 ? '#0a7a4a' : '#b00020' }}>
                    {fmt.pct(p.change_pct)}
                  </td>
                  <td className="text-right">${fmt.price(p.high)}</td>
                  <td className="text-right">${fmt.price(p.low)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {/* SIGNALS */}
      <section className="mb-4">
        <h2 className="text-xs font-bold uppercase tracking-widest border-b border-gray-300 mb-2">PULSE Signal</h2>
        <table className="w-full text-[12px] font-mono">
          <thead>
            <tr className="text-gray-600 text-[10px] uppercase">
              <th className="text-left py-1">Asset</th>
              <th className="text-right">Score</th>
              <th className="text-right">Verdict</th>
              <th className="text-right">Conviction</th>
              <th className="text-left pl-4">Key Risk</th>
            </tr>
          </thead>
          <tbody>
            {ASSETS.map(a => {
              const s = signal[a.key] ?? {};
              const score = s.score;
              return (
                <tr key={a.key} className="border-t border-gray-200">
                  <td className="py-1.5"><strong>{a.label}</strong></td>
                  <td className="text-right">{score !== undefined ? `${score >= 0 ? '+' : ''}${score.toFixed(2)}` : '—'}</td>
                  <td className="text-right" style={{ color: score >= 0.4 ? '#0a7a4a' : score <= -0.4 ? '#b00020' : '#b8941f' }}>
                    <strong>{signalLabel(score)}</strong>
                  </td>
                  <td className="text-right">{s.conviction ?? '—'}</td>
                  <td className="text-left pl-4 text-[10px] text-gray-700">{s.key_risk ?? '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {/* TRADE IDEA + FAIR VALUE */}
      <section className="mb-4 grid grid-cols-2 gap-6">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-widest border-b border-gray-300 mb-2">Trade Idea · Brent</h2>
          {tradeIdea ? (
            <div className="text-[11px] font-mono space-y-1">
              <div><strong>Direction:</strong> <span style={{ color: tradeIdea.direction === 'LONG' ? '#0a7a4a' : tradeIdea.direction === 'SHORT' ? '#b00020' : '#b8941f' }}>{tradeIdea.direction}</span></div>
              <div><strong>Spot:</strong> ${fmt.price(tradeIdea.live_price)}</div>
              <div><strong>Target:</strong> ${fmt.price(tradeIdea.target_level)}</div>
              <div><strong>Stop:</strong> ${fmt.price(tradeIdea.stop_level)}</div>
              <div><strong>Horizon:</strong> {tradeIdea.time_horizon ?? '—'}</div>
              {tradeIdea.entry_thesis && (
                <div className="mt-2 pt-2 border-t border-gray-200">
                  <strong>Thesis:</strong>
                  <div className="text-[10.5px] mt-1 text-gray-700">{Array.isArray(tradeIdea.entry_thesis) ? tradeIdea.entry_thesis.join(' ') : tradeIdea.entry_thesis}</div>
                </div>
              )}
              {tradeIdea.key_risk && (
                <div className="mt-1.5 text-[10.5px] text-gray-700">
                  <strong>Risk:</strong> {tradeIdea.key_risk}
                </div>
              )}
            </div>
          ) : <div className="text-[11px] text-gray-500">(no trade idea cached)</div>}
        </div>

        <div>
          <h2 className="text-xs font-bold uppercase tracking-widest border-b border-gray-300 mb-2">Fair Value · Brent</h2>
          {fv.fair_value ? (
            <div className="text-[11px] font-mono space-y-1">
              <div><strong>Spot:</strong> ${fmt.price(fv.live_price)}</div>
              <div><strong>Model:</strong> ${fmt.price(fv.fair_value)}</div>
              <div><strong>Deviation:</strong> <span style={{ color: (fv.deviation_pct ?? 0) > 0 ? '#b00020' : '#0a7a4a' }}>
                {fv.deviation_pct >= 0 ? '+' : ''}{fv.deviation_pct?.toFixed(1)}%
              </span></div>
              <div><strong>Label:</strong> {fv.deviation_label ?? '—'}</div>
              {fv.components && (
                <div className="mt-2 pt-2 border-t border-gray-200 space-y-0.5 text-[10.5px]">
                  <div><strong>Components:</strong></div>
                  {Object.entries(fv.components).map(([k, c]: any) => (
                    <div key={k} className="flex justify-between">
                      <span className="text-gray-600">{k.replace(/_/g, ' ')}</span>
                      <span>{c.value >= 0 ? '+' : ''}${c.value.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : <div className="text-[11px] text-gray-500">(model warming)</div>}
        </div>
      </section>

      {/* KEY FUNDAMENTALS */}
      <section className="mb-4">
        <h2 className="text-xs font-bold uppercase tracking-widest border-b border-gray-300 mb-2">Key Fundamentals</h2>
        <div className="grid grid-cols-4 gap-4 text-[11px] font-mono">
          <div>
            <div className="text-[10px] text-gray-600 uppercase">US Crude Stocks</div>
            <div className="text-base font-bold">{inv.current ? Math.round(inv.current / 1000) : '—'} MMbbl</div>
            <div className="text-[10px]" style={{ color: (inv.deviation_pct ?? 0) > 0 ? '#b00020' : '#0a7a4a' }}>
              {inv.deviation_pct !== undefined ? `${inv.deviation_pct >= 0 ? '+' : ''}${inv.deviation_pct.toFixed(1)}% vs 5y` : '—'}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-gray-600 uppercase">Days Forward Cover</div>
            <div className="text-base font-bold">{fcov.current ? fcov.current.toFixed(1) : '—'} d</div>
            <div className="text-[10px] text-gray-600">critical {fcov.critical_low ?? 54}d</div>
          </div>
          <div>
            <div className="text-[10px] text-gray-600 uppercase">COT Crude (MM)</div>
            <div className="text-base font-bold">{cot.percentile ? `${cot.percentile.toFixed(0)}%ile` : '—'}</div>
            <div className="text-[10px] text-gray-600">{cot.label ?? '—'}</div>
          </div>
          <div>
            <div className="text-[10px] text-gray-600 uppercase">Geo Risk</div>
            <div className="text-base font-bold">{geo.index ? geo.index.toFixed(0) : '—'}/100</div>
            <div className="text-[10px] text-gray-600">{geo.label ?? '—'}</div>
          </div>
        </div>
      </section>

      {/* SPREADS + CURVE */}
      <section className="mb-4 grid grid-cols-2 gap-6">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-widest border-b border-gray-300 mb-2">Spreads</h2>
          <table className="w-full text-[11px] font-mono">
            <tbody>
              <tr><td className="py-0.5">Brent M1-M2</td><td className="text-right">{m1m2 !== null ? `${m1m2 >= 0 ? '+' : ''}${m1m2.toFixed(2)}` : '—'}</td></tr>
              <tr><td className="py-0.5">Brent − WTI</td><td className="text-right">{brtWti !== null ? `+$${brtWti.toFixed(2)}` : '—'}</td></tr>
              <tr><td className="py-0.5">3-2-1 Crack</td><td className="text-right">${cracks.crack_321?.value?.toFixed(2) ?? '—'} <span className="text-gray-500 text-[9px]">({cracks.crack_321?.signal ?? '—'})</span></td></tr>
              <tr><td className="py-0.5">Gasoline Crack</td><td className="text-right">${cracks.gasoline_crack?.value?.toFixed(2) ?? '—'}</td></tr>
              <tr><td className="py-0.5">Distillate Crack</td><td className="text-right">${cracks.heating_oil_crack?.value?.toFixed(2) ?? '—'}</td></tr>
            </tbody>
          </table>
        </div>

        <div>
          <h2 className="text-xs font-bold uppercase tracking-widest border-b border-gray-300 mb-2">Brent Forward Curve</h2>
          <table className="w-full text-[11px] font-mono">
            <tbody>
              {bc.slice(0, 12).map((c: any, i: number) => (
                <tr key={i} className={i % 2 ? 'bg-gray-50' : ''}>
                  <td className="py-0.5 pl-1">M{i + 1}</td>
                  <td className="text-right pr-1">{c.price ? `$${c.price.toFixed(2)}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* FOOTER */}
      <div className="mt-6 pt-3 border-t border-gray-300 text-[9px] font-mono text-gray-600 text-center">
        PULSE Energy Intelligence Terminal · Sources: yfinance, EIA API v2, CFTC COT, Open-Meteo, FRED ·
        For analytical use only. Not investment advice.
      </div>
    </div>
  );
}
