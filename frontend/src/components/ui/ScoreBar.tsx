type Props = {
  score: number; // -2 .. +2
  height?: number;
  showLabels?: boolean;
};

export function ScoreBar({ score, height = 8, showLabels = false }: Props) {
  const clamped = Math.max(-2, Math.min(2, score ?? 0));
  const pct = Math.abs(clamped) / 2 * 50; // half width per side
  const positive = clamped >= 0;
  const color = positive ? '#10d997' : '#ff4d6d';

  return (
    <div className="w-full">
      <div className="relative w-full bg-bg-elev rounded overflow-hidden" style={{ height }}>
        <div className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
        <div
          className="absolute inset-y-0 transition-all duration-700 ease-out rounded"
          style={{
            left: positive ? '50%' : `${50 - pct}%`,
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}55, ${color})`,
            boxShadow: `0 0 12px ${color}66`,
          }}
        />
      </div>
      {showLabels && (
        <div className="flex justify-between text-[9px] text-text-muted font-mono mt-1 tabular">
          <span>-2.0</span>
          <span>0</span>
          <span>+2.0</span>
        </div>
      )}
    </div>
  );
}
