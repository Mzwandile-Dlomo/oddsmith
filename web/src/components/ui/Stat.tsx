import { type ReactNode } from "react";

type Tone = "default" | "success" | "danger" | "warn" | "accent";

const toneClasses: Record<Tone, string> = {
  default: "text-ink",
  success: "text-success",
  danger: "text-danger",
  warn: "text-warn",
  accent: "text-accent",
};

/**
 * Resolves a signed number to a tone so callers stop re-deriving the same
 * green/red/neutral ternary at every call site.
 */
export function signTone(value: number, neutral = false): Tone {
  if (neutral) return "default";
  return value > 0 ? "success" : value < 0 ? "danger" : "default";
}

export function Stat({
  label,
  value,
  detail,
  tone = "default",
  size = "md",
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: Tone;
  size?: "sm" | "md" | "lg";
}) {
  const valueSize =
    size === "lg" ? "text-xl sm:text-2xl" : size === "sm" ? "text-sm" : "text-base sm:text-lg";

  return (
    <div className="flex min-w-0 flex-col gap-0.5 bg-surface px-3 py-2.5 sm:px-4 sm:py-3">
      <p className="truncate text-[10px] font-semibold uppercase tracking-widest text-faint">
        {label}
      </p>
      <p
        className={`truncate font-semibold tabular-nums tracking-tight ${valueSize} ${toneClasses[tone]}`}
      >
        {value}
      </p>
      {detail && <p className="truncate text-[11px] text-muted">{detail}</p>}
    </div>
  );
}

/**
 * Tiles reflow on available width rather than being pinned to a column count,
 * so the same row reads correctly at 320px and spreads across a wide monitor
 * instead of leaving a gutter. `minmax(0,1fr)` keeps `truncate` working.
 */
export function StatGrid({
  children,
  min = "9rem",
  className = "",
}: {
  children: ReactNode;
  /** Narrowest a tile may get before the grid drops a column. */
  min?: string;
  className?: string;
}) {
  return (
    <div
      className={`grid gap-px overflow-hidden rounded-2xl border border-border bg-border shadow-card ${className}`}
      style={{ gridTemplateColumns: `repeat(auto-fit, minmax(min(${min}, 100%), 1fr))` }}
    >
      {children}
    </div>
  );
}
