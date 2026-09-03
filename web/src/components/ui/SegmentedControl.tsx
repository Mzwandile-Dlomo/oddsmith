"use client";

import { type ReactNode } from "react";

export interface Segment<T extends string | number> {
  value: T;
  label: ReactNode;
  /** Renders the segment inert, with the reason surfaced as visible help text. */
  disabledReason?: string;
}

/**
 * A single row of mutually exclusive choices — timeframes, target odds, leg
 * counts. Segments meet the 44px touch minimum on phones, tighten from `sm`,
 * and the row scrolls rather than wrapping into a ragged second line.
 */
export function SegmentedControl<T extends string | number>({
  value,
  onChange,
  segments,
  label,
  fill = false,
  className = "",
}: {
  value: T;
  onChange: (value: T) => void;
  segments: Segment<T>[];
  /** Accessible name for the group. */
  label: string;
  /** Stretch segments to share the full width instead of hugging their labels. */
  fill?: boolean;
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={`scroll-x inline-flex max-w-full items-center gap-1 rounded-xl border border-border bg-surface p-1 shadow-card ${
        fill ? "w-full" : ""
      } ${className}`}
    >
      {segments.map((segment) => {
        const active = segment.value === value;
        const disabled = Boolean(segment.disabledReason);
        return (
          <button
            key={String(segment.value)}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            title={segment.disabledReason}
            onClick={() => onChange(segment.value)}
            className={`flex min-h-[44px] flex-1 shrink-0 items-center justify-center whitespace-nowrap rounded-lg px-3 text-sm font-medium transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[32px] ${
              disabled
                ? "cursor-not-allowed text-faint opacity-60"
                : active
                  ? "bg-accent text-white shadow-sm"
                  : "text-muted hover:bg-hairline hover:text-ink"
            }`}
          >
            {segment.label}
          </button>
        );
      })}
    </div>
  );
}
