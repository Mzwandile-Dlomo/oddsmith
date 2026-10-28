"use client";

import Link from "next/link";
import type { CalendarDay } from "@/lib/types";
import { dateFromISO, formatCompactSigned, formatSignedCurrency } from "@/lib/utils";

/**
 * P&L drives the cell's background so a month reads as a performance heatmap at
 * a glance; everything else is detail you only look at once a cell catches your
 * eye. Days with no settled slip stay neutral rather than being tinted by a
 * pending bet's notional.
 */
function pnlTone(day: CalendarDay): string {
  const settled = day.won_count + day.lost_count;
  if (settled === 0) return "";
  if (day.profit_loss > 0) return "bg-success-soft/60";
  if (day.profit_loss < 0) return "bg-danger-soft/60";
  return "bg-hairline";
}

function pnlText(day: CalendarDay): string {
  return day.profit_loss > 0
    ? "text-success"
    : day.profit_loss < 0
      ? "text-danger"
      : "text-muted";
}

function ConfidenceDot({ day }: { day: CalendarDay }) {
  if (!day.model) return null;
  const { target_met, combined_model_prob } = day.model;
  if (!target_met) {
    return (
      <span
        title="No slip clears the target on this card"
        className="h-1.5 w-1.5 shrink-0 rounded-full bg-border"
      />
    );
  }
  // Banker slips live in a narrow band; 65% is the line between "playable" and
  // "strong" for a target-odds accumulator.
  const strong = combined_model_prob >= 0.65;
  return (
    <span
      title={`Model: ${(combined_model_prob * 100).toFixed(0)}% at ${day.model.combined_odds.toFixed(2)}`}
      className={`h-1.5 w-1.5 shrink-0 rounded-full ${strong ? "bg-success" : "bg-warn"}`}
    />
  );
}

/**
 * A 7-column month can only give a phone ~45px per cell, so the cell sheds
 * detail as it narrows: the day number and the model dot survive everywhere,
 * match counts appear from `sm`, league names only from `lg`. Everything the
 * cell drops is still on the day page a tap away.
 */
export function DayCell({
  day,
  inMonth,
  isToday,
  currency,
}: {
  day: CalendarDay;
  inMonth: boolean;
  isToday: boolean;
  currency: string;
}) {
  const dayNumber = dateFromISO(day.date).getDate();
  const settled = day.won_count + day.lost_count;
  const hasFixtures = day.fixture_count > 0;

  return (
    <Link
      href={`/matches/calendar/${day.date}`}
      aria-label={`${day.date}, ${day.fixture_count} matches`}
      className={`group relative flex min-h-[62px] flex-col gap-0.5 border-b border-r border-border p-1 transition-colors sm:min-h-[92px] sm:gap-1 sm:p-2 lg:min-h-[112px] ${
        inMonth ? pnlTone(day) : "bg-canvas"
      } ${inMonth ? "hover:bg-accent-light/70" : "hover:bg-hairline"}`}
    >
      <div className="flex items-center justify-between gap-0.5">
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold tabular-nums sm:text-xs ${
            isToday
              ? "bg-accent text-canvas"
              : inMonth
                ? "text-ink"
                : "text-outline"
          }`}
        >
          {dayNumber}
        </span>
        <ConfidenceDot day={day} />
      </div>

      {inMonth && hasFixtures && (
        <span className="hidden text-[11px] font-medium text-muted sm:block">
          {day.fixture_count} {day.fixture_count === 1 ? "match" : "matches"}
        </span>
      )}

      {inMonth && day.leagues.length > 0 && (
        <span className="hidden truncate text-[10px] leading-tight text-faint lg:block">
          {day.leagues.slice(0, 2).join(" · ")}
          {day.leagues.length > 2 && ` +${day.leagues.length - 2}`}
        </span>
      )}

      <div className="mt-auto flex flex-col gap-0.5">
        {settled > 0 && (
          <span className={`text-[10px] font-semibold tabular-nums sm:text-xs ${pnlText(day)}`}>
            {/* The currency prefix will not fit a phone column. */}
            <span className="sm:hidden">{formatCompactSigned(day.profit_loss)}</span>
            <span className="hidden sm:inline">
              {formatSignedCurrency(day.profit_loss, currency)}
            </span>
          </span>
        )}
        {day.pending_count > 0 && (
          <span className="text-[10px] font-medium leading-none text-warn">
            <span className="sm:hidden">●{day.pending_count}</span>
            <span className="hidden sm:inline">{day.pending_count} open</span>
          </span>
        )}
        {/* On a phone the match count is dropped above, so a bare dot keeps
            "this day has a card" visible without costing a line of text. */}
        {inMonth && hasFixtures && settled === 0 && day.pending_count === 0 && (
          <span
            aria-hidden
            className="h-1 w-1 rounded-full bg-outline sm:hidden"
          />
        )}
      </div>
    </Link>
  );
}
