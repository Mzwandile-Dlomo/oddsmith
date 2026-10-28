"use client";

import { useEffect, useMemo, useState } from "react";
import { LineChart } from "lucide-react";
import type { SlipView } from "@/lib/types";
import { formatSignedCurrency } from "@/lib/utils";

interface Point {
  index: number;
  name: string;
  settledAt: string;
  change: number;
  cumulative: number;
}

/** Running profit after each settled slip, in settlement order. */
export function cumulativePnl(slips: SlipView[]): Point[] {
  const settled = slips
    .filter((s) => s.result !== "pending" && s.settled_at)
    .sort((a, b) => (a.settled_at ?? "").localeCompare(b.settled_at ?? ""));
  let running = 0;
  return settled.map((slip, index) => {
    running += slip.profit_loss;
    return {
      index: index + 1,
      name: slip.name ?? `Slip #${slip.id}`,
      settledAt: slip.settled_at ?? "",
      change: slip.profit_loss,
      cumulative: running,
    };
  });
}

/** Clean, rounded tick values that always include zero. */
function niceTicks(min: number, max: number, count = 4): number[] {
  const lo = Math.min(min, 0);
  const hi = Math.max(max, 0);
  const span = hi - lo || 1;
  const raw = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];
  for (let v = Math.floor(lo / step) * step; v <= hi + step * 0.001; v += step) {
    ticks.push(Number(v.toFixed(10)));
  }
  if (ticks[ticks.length - 1] < hi) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

function compact(value: number): string {
  const abs = Math.abs(value);
  const text = abs >= 1000 ? `${(abs / 1000).toFixed(abs >= 10000 ? 0 : 1)}K` : `${Math.round(abs)}`;
  return value < 0 ? `−${text}` : text;
}

const HEIGHT = 220;
const PAD = { top: 14, right: 16, bottom: 26, left: 44 };

export function PnlChart({ slips, currency }: { slips: SlipView[]; currency: string }) {
  const points = useMemo(() => cumulativePnl(slips), [slips]);
  // A callback ref, because the frame mounts only once data arrives: an effect
  // keyed on a plain ref would run before that and never measure it.
  const [frame, setFrame] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  // Measured, not scaled through a viewBox, so text and 2px lines stay crisp.
  useEffect(() => {
    if (!frame) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(frame);
    return () => observer.disconnect();
  }, [frame]);

  if (points.length < 2) {
    return (
      <div className="flex h-[220px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border text-center">
        <LineChart size={20} className="text-faint" />
        <p className="text-sm font-medium text-ink">Not enough settled slips yet</p>
        <p className="max-w-xs text-xs text-muted">
          The profit line appears after two settled slips. {points.length} settled so far.
        </p>
      </div>
    );
  }

  const values = points.map((p) => p.cumulative);
  const ticks = niceTicks(Math.min(...values), Math.max(...values));
  const yMin = ticks[0];
  const yMax = ticks[ticks.length - 1];
  const plotW = Math.max(width - PAD.left - PAD.right, 1);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + ((i - 1) / (points.length - 1)) * plotW;
  const y = (v: number) => PAD.top + (1 - (v - yMin) / (yMax - yMin || 1)) * plotH;

  const line = points.map((p) => `${x(p.index)},${y(p.cumulative)}`).join(" L");
  const area = `M${x(1)},${y(0)} L${line} L${x(points.length)},${y(0)} Z`;
  const last = points[points.length - 1];
  const active = hover === null ? null : points[hover];

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const rel = (e.clientX - box.left - PAD.left) / plotW;
    setHover(Math.min(points.length - 1, Math.max(0, Math.round(rel * (points.length - 1)))));
  }

  return (
    <div className="flex flex-col gap-3">
      <div ref={setFrame} className="relative h-[220px] w-full">
        {width > 0 && (
          <svg
            width={width}
            height={HEIGHT}
            role="img"
            aria-label={`Cumulative profit across ${points.length} settled slips, ending at ${formatSignedCurrency(last.cumulative, currency)}`}
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
            className="touch-none select-none"
          >
            {ticks.map((t) => (
              <g key={t}>
                <line
                  x1={PAD.left}
                  x2={PAD.left + plotW}
                  y1={y(t)}
                  y2={y(t)}
                  stroke="var(--color-hairline)"
                  strokeWidth={t === 0 ? 1.5 : 1}
                />
                <text
                  x={PAD.left - 8}
                  y={y(t)}
                  textAnchor="end"
                  dominantBaseline="middle"
                  className="fill-faint text-[11px] tabular-nums"
                >
                  {compact(t)}
                </text>
              </g>
            ))}
            <text
              x={PAD.left}
              y={HEIGHT - 6}
              className="fill-faint text-[11px]"
            >
              First settled
            </text>
            <text
              x={PAD.left + plotW}
              y={HEIGHT - 6}
              textAnchor="end"
              className="fill-faint text-[11px]"
            >
              Latest
            </text>

            <path d={area} fill="var(--color-accent)" fillOpacity={0.1} />
            <path
              d={`M${line}`}
              fill="none"
              stroke="var(--color-accent)"
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />

            {active && (
              <line
                x1={x(active.index)}
                x2={x(active.index)}
                y1={PAD.top}
                y2={PAD.top + plotH}
                stroke="var(--color-outline)"
                strokeWidth={1}
              />
            )}
            {(active ? [active] : [last]).map((p) => (
              <circle
                key={p.index}
                cx={x(p.index)}
                cy={y(p.cumulative)}
                r={4}
                fill="var(--color-accent)"
                stroke="var(--color-surface)"
                strokeWidth={2}
              />
            ))}
          </svg>
        )}

        {active && (
          <div
            className="pointer-events-none absolute top-0 z-10 w-52 rounded-lg border border-border bg-canvas/95 px-3 py-2 text-xs shadow-raised"
            style={{
              left: Math.min(Math.max(x(active.index) - 104, 0), Math.max(width - 208, 0)),
            }}
          >
            <p className="truncate font-medium text-ink">{active.name}</p>
            <p className="text-faint">
              {new Date(active.settledAt).toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </p>
            <p className="mt-1 flex justify-between gap-2 text-muted">
              This slip
              <span className="tabular-nums text-ink">{formatSignedCurrency(active.change, currency)}</span>
            </p>
            <p className="flex justify-between gap-2 text-muted">
              Running total
              <span className="font-semibold tabular-nums text-ink">
                {formatSignedCurrency(active.cumulative, currency)}
              </span>
            </p>
          </div>
        )}
      </div>

      <details className="group text-xs text-muted">
        <summary className="cursor-pointer select-none text-faint hover:text-ink">View as table</summary>
        <div className="scroll-x mt-2 rounded-lg border border-border">
          <table className="w-full text-left">
            <thead className="text-faint">
              <tr>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">Slip</th>
                <th className="px-3 py-2 font-medium">Settled</th>
                <th className="px-3 py-2 text-right font-medium">P&amp;L</th>
                <th className="px-3 py-2 text-right font-medium">Running</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.index} className="border-t border-hairline">
                  <td className="px-3 py-2 tabular-nums">{p.index}</td>
                  <td className="max-w-[12rem] truncate px-3 py-2 text-ink">{p.name}</td>
                  <td className="px-3 py-2">{p.settledAt.slice(0, 10)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatSignedCurrency(p.change, currency)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-ink">
                    {formatSignedCurrency(p.cumulative, currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
