type Props = {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
  positiveColor?: string;
  negativeColor?: string;
};

export function Sparkline({
  data,
  width = 96,
  height = 28,
  className,
  positiveColor = '#10d997',
  negativeColor = '#ff4d6d',
}: Props) {
  if (!data || data.length < 2) {
    return <svg width={width} height={height} className={className} />;
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = width / (data.length - 1);
  const pts = data.map((v, i) => [i * stepX, height - ((v - min) / range) * height]);
  const path = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  const isUp = data[data.length - 1] >= data[0];
  const color = isUp ? positiveColor : negativeColor;
  const last = pts[pts.length - 1];

  return (
    <svg width={width} height={height} className={className}>
      <defs>
        <linearGradient id={`spark-${color}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d={`${path} L ${last[0]} ${height} L 0 ${height} Z`}
        fill={`url(#spark-${color})`}
      />
      <path d={path} stroke={color} strokeWidth="1.5" fill="none" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="2" fill={color} />
    </svg>
  );
}
