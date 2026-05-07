"use client";

import { useState } from "react";
import type { TrafficPoint } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Hand-rolled SVG line chart for the traffic series. Two overlaid lines
 * (total views, unique visitors). Hover a vertical band to highlight the
 * day and surface a tooltip — no chart library, ~120 LOC.
 */
export function TrafficChart({
  series,
  className,
  height = 140,
}: {
  series: TrafficPoint[];
  className?: string;
  height?: number;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (series.length === 0) {
    return (
      <div
        className={cn(
          "rounded-lg border border-zinc-800 bg-zinc-950/40 p-6 text-center text-xs text-zinc-500",
          className,
        )}
        style={{ height }}
      >
        No traffic recorded yet. Daily snapshots accrue as RepoLens runs.
      </div>
    );
  }

  const totalIsZero = series.every((p) => p.views === 0 && p.unique_views === 0);
  const padX = 6;
  const padY = 8;
  const viewBoxW = Math.max(series.length * 14, 280);
  const viewBoxH = height;
  const usableW = viewBoxW - padX * 2;
  const usableH = viewBoxH - padY * 2 - 18; // 18px reserved for axis labels

  const maxValue = Math.max(
    1,
    ...series.flatMap((p) => [p.views, p.unique_views]),
  );

  const stepX = series.length > 1 ? usableW / (series.length - 1) : 0;
  const yFor = (v: number) => padY + (1 - v / maxValue) * usableH;
  const xFor = (i: number) => padX + i * stepX;

  const linePath = (key: keyof TrafficPoint) =>
    series
      .map((p, i) => `${i === 0 ? "M" : "L"} ${xFor(i).toFixed(2)} ${yFor((p[key] as number) ?? 0).toFixed(2)}`)
      .join(" ");

  const hovered = hoverIdx !== null ? series[hoverIdx] : null;

  return (
    <div className={cn("relative", className)}>
      <svg
        width="100%"
        height={viewBoxH}
        viewBox={`0 0 ${viewBoxW} ${viewBoxH}`}
        preserveAspectRatio="none"
        onMouseLeave={() => setHoverIdx(null)}
      >
        {/* y-axis gridlines (3 reference levels) */}
        {[0.25, 0.5, 0.75].map((p) => {
          const y = padY + p * usableH;
          return (
            <line
              key={p}
              x1={padX}
              x2={viewBoxW - padX}
              y1={y}
              y2={y}
              stroke="rgb(63 63 70)"
              strokeOpacity={0.4}
              strokeWidth={0.5}
              strokeDasharray="2 3"
            />
          );
        })}

        {/* views (filled) */}
        <path
          d={`${linePath("views")} L ${xFor(series.length - 1).toFixed(2)} ${(padY + usableH).toFixed(2)} L ${xFor(0).toFixed(2)} ${(padY + usableH).toFixed(2)} Z`}
          fill="rgb(20 184 166)"
          fillOpacity={0.15}
        />
        <path d={linePath("views")} fill="none" stroke="rgb(94 234 212)" strokeWidth={1.5} />

        {/* unique visitors (line, fainter) */}
        <path d={linePath("unique_views")} fill="none" stroke="rgb(244 114 182)" strokeWidth={1.25} strokeDasharray="3 2" />

        {/* invisible hit-area columns */}
        {series.map((_, i) => {
          const w = stepX > 0 ? stepX : viewBoxW;
          return (
            <rect
              key={i}
              x={xFor(i) - w / 2}
              y={0}
              width={w}
              height={viewBoxH - 18}
              fill="transparent"
              onMouseEnter={() => setHoverIdx(i)}
            />
          );
        })}

        {/* hover marker */}
        {hoverIdx !== null && (
          <line
            x1={xFor(hoverIdx)}
            x2={xFor(hoverIdx)}
            y1={padY}
            y2={padY + usableH}
            stroke="rgb(228 228 231)"
            strokeOpacity={0.4}
            strokeWidth={0.75}
          />
        )}

        {/* axis labels (first / last day) */}
        {series.length > 0 && (
          <>
            <text
              x={xFor(0)}
              y={viewBoxH - 4}
              fill="rgb(113 113 122)"
              fontSize="9"
              textAnchor="start"
            >
              {fmtDate(series[0].day)}
            </text>
            <text
              x={xFor(series.length - 1)}
              y={viewBoxH - 4}
              fill="rgb(113 113 122)"
              fontSize="9"
              textAnchor="end"
            >
              {fmtDate(series[series.length - 1].day)}
            </text>
          </>
        )}
      </svg>

      {/* legend */}
      <div className="absolute top-2 right-2 flex gap-3 text-[10px] text-zinc-400">
        <LegendDot color="rgb(94 234 212)" label="Views" />
        <LegendDot color="rgb(244 114 182)" label="Unique" dashed />
      </div>

      {/* tooltip */}
      {hovered && (
        <div className="absolute top-2 left-2 rounded-md bg-zinc-900/90 border border-zinc-800 px-2 py-1 text-[10px] text-zinc-300 pointer-events-none">
          <div className="font-medium text-zinc-100">{fmtDate(hovered.day, true)}</div>
          <div>
            <span className="text-teal-300">{hovered.views}</span> views ·{" "}
            <span className="text-pink-300">{hovered.unique_views}</span> unique
          </div>
          {hovered.clones > 0 && (
            <div className="text-zinc-500">
              {hovered.clones} clones / {hovered.unique_clones} unique
            </div>
          )}
        </div>
      )}

      {totalIsZero && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-xs text-zinc-500 bg-zinc-900/70 px-2 py-1 rounded-md">
            All zeros — no public traffic in this window.
          </div>
        </div>
      )}
    </div>
  );
}

function LegendDot({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1">
      <svg width="12" height="2">
        <line
          x1="0"
          y1="1"
          x2="12"
          y2="1"
          stroke={color}
          strokeWidth="1.5"
          strokeDasharray={dashed ? "3 2" : undefined}
        />
      </svg>
      {label}
    </span>
  );
}

function fmtDate(iso: string, includeYear = false): string {
  const d = new Date(iso + "T00:00:00Z");
  const opts: Intl.DateTimeFormatOptions = includeYear
    ? { month: "short", day: "numeric", year: "numeric" }
    : { month: "short", day: "numeric" };
  return d.toLocaleDateString(undefined, opts);
}
