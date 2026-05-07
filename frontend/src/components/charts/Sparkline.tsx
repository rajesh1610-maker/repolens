"use client";

/**
 * Hand-rolled SVG sparkline. Zero dependencies — see decision D-7.1.
 *
 * Renders as a thin polyline that auto-scales to the data's min/max.
 * If every value is the same (or all zeros), draws a flat line at the
 * vertical centre — never an empty SVG.
 *
 * Props
 *   data:      sequence of numbers, oldest → newest
 *   width:     pixel width  (default 80)
 *   height:    pixel height (default 24)
 *   className: passed through to the <svg>
 */
export function Sparkline({
  data,
  width = 80,
  height = 24,
  className,
}: {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
}) {
  if (data.length === 0) {
    return (
      <svg
        width={width}
        height={height}
        className={className}
        viewBox={`0 0 ${width} ${height}`}
        aria-label="empty sparkline"
      >
        <line
          x1={1}
          x2={width - 1}
          y1={height / 2}
          y2={height / 2}
          stroke="currentColor"
          strokeOpacity={0.15}
          strokeWidth={1}
          strokeDasharray="2 3"
        />
      </svg>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = (width - 2) / Math.max(data.length - 1, 1);

  const points = data
    .map((v, i) => {
      const x = 1 + i * stepX;
      const y = height - 1 - ((v - min) / range) * (height - 2);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const last = data[data.length - 1];
  const lastX = 1 + (data.length - 1) * stepX;
  const lastY = height - 1 - ((last - min) / range) * (height - 2);

  return (
    <svg
      width={width}
      height={height}
      className={className}
      viewBox={`0 0 ${width} ${height}`}
      aria-label={`sparkline ${data[0]} → ${last}`}
      role="img"
    >
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.25}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r={1.6} fill="currentColor" />
    </svg>
  );
}
