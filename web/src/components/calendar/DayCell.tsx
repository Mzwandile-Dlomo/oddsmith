"use client";

import Link from "next/link";
import type { CalendarDay } from "@/lib/types";
import { dateFromISO, formatSignedCurrency } from "@/lib/utils";

/**
 * P&L drives the cell's background so a month reads as a performance heatmap at
 * a glance; everything else is detail you only look at once a cell catches your
 * eye. Days with no settled slip stay neutral rather than being tinted by a
 * pending bet's notional.
 */
function pnlTone(day: CalendarDay): string {
  const settled = day.won_count + day.lost_count;
  if (settled === 0) return "";
  if (day.profit_loss > 0) return "bg-[#D1FAE5]/60";
  if (day.profit_loss < 0) return "bg-[#FEE2E2]/60";
  return "bg-[#F3F4F6]";
}

function ConfidenceDot({ day }: { day: CalendarDay }) {
  if (!day.model) return null;
  const { target_met, combined_model_prob } = day.model;
  if (!target_met) {
    return (
      <span
        title="No slip clears the target on this card"
        className="h-1.5 w-1.5 rounded-full bg-[#E5E7EB]"
      />
    );
  }
  // Banker slips live in a narrow band; 65% is the line between "playable" and
  // "strong" for a target-odds accumulator.
  const strong = combined_model_prob >= 0.65;
  return (
    <span
      title={`Model: ${(combined_model_prob * 100).toFixed(0)}% at ${day.model.combined_odds.toFixed(2)}`}
      className={`h-1.5 w-1.5 rounded-full ${strong ? "bg-[#059669]" : "bg-[#D97706]"}`}
    />
  );
}

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
      href={`/calendar/${day.date}`}
      className={`group relative flex min-h-[104px] flex-col gap-1 border-b border-r border-[#E5E7EB] p-2 transition-colors ${
        inMonth ? pnlTone(day) : "bg-[#FAFAFA]"
      } ${inMonth ? "hover:bg-[#EEE9FF]/70" : "hover:bg-[#F3F4F6]"}`}
    >
      <div className="flex items-center justify-between">
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold tabular-nums ${
            isToday
              ? "bg-[#6C47FF] text-white"
              : inMonth
                ? "text-[#111827]"
                : "text-[#D1D5DB]"
          }`}
        >
          {dayNumber}
        </span>
        <ConfidenceDot day={day} />
      </div>

      {inMonth && hasFixtures && (
        <span className="text-[11px] font-medium text-[#6B7280]">
          {day.fixture_count} {day.fixture_count === 1 ? "match" : "matches"}
        </span>
      )}

      {inMonth && day.leagues.length > 0 && (
        <span className="truncate text-[10px] leading-tight text-[#9CA3AF]">
          {day.leagues.slice(0, 2).join(" · ")}
          {day.leagues.length > 2 && ` +${day.leagues.length - 2}`}
        </span>
      )}

      <div className="mt-auto flex flex-col gap-0.5">
        {settled > 0 && (
          <span
            className={`text-xs font-semibold tabular-nums ${
              day.profit_loss > 0
                ? "text-[#059669]"
                : day.profit_loss < 0
                  ? "text-[#DC2626]"
                  : "text-[#6B7280]"
            }`}
          >
            {formatSignedCurrency(day.profit_loss, currency)}
          </span>
        )}
        {day.pending_count > 0 && (
          <span className="text-[10px] font-medium text-[#D97706]">
            {day.pending_count} open
          </span>
        )}
      </div>
    </Link>
  );
}
