"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, CalendarDays } from "lucide-react";
import { fetchCalendar, fetchSlips } from "@/lib/api";
import type { CalendarDay, SlipView } from "@/lib/types";
import {
  addDays,
  dateFromISO,
  formatSignedCurrency,
  toLocalISODate,
  todayISO,
} from "@/lib/utils";
import { DailyAcca } from "@/components/generator/DailyAcca";
import { SlipCard } from "@/components/slips/SlipCard";
import { slipMatchDay } from "@/components/calendar/DayView";

/** Pending slips whose last kickoff has passed — these are waiting on you. */
function needsSettling(slips: SlipView[]): SlipView[] {
  const now = Date.now();
  return slips.filter((slip) => {
    if (slip.result !== "pending" || slip.legs.length === 0) return false;
    const last = slip.legs
      .map((l) => new Date(l.kickoff_utc).getTime())
      .reduce((a, b) => Math.max(a, b), 0);
    // Roughly a full match plus stoppage; before that the result isn't known.
    return now > last + 2 * 60 * 60 * 1000;
  });
}

function UpcomingStrip({ days }: { days: CalendarDay[] }) {
  if (days.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {days.map((day) => {
        const d = dateFromISO(day.date);
        const playable = day.model?.target_met;
        return (
          <Link
            key={day.date}
            href={`/calendar/${day.date}`}
            className="flex flex-col gap-1 rounded-xl border border-[#E5E7EB] bg-white px-3 py-2.5 transition-colors hover:border-[#6C47FF]/40 hover:bg-[#EEE9FF]/40"
          >
            <span className="text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
              {d.toLocaleDateString(undefined, { weekday: "short", day: "numeric" })}
            </span>
            <span className="text-sm font-semibold tabular-nums text-[#111827]">
              {day.fixture_count}
              <span className="ml-1 text-[11px] font-normal text-[#9CA3AF]">
                {day.fixture_count === 1 ? "match" : "matches"}
              </span>
            </span>
            <span
              className={`text-[11px] font-medium ${
                playable ? "text-[#059669]" : "text-[#9CA3AF]"
              }`}
            >
              {playable
                ? `${Math.round((day.model?.combined_model_prob ?? 0) * 100)}% @ ${day.model?.combined_odds.toFixed(2)}`
                : day.fixture_count === 0
                  ? "No card"
                  : "No target slip"}
            </span>
          </Link>
        );
      })}
    </div>
  );
}

export function TodayView() {
  const today = todayISO();
  const weekEnd = toLocalISODate(addDays(dateFromISO(today), 6));

  const { data: slips } = useQuery({ queryKey: ["slips"], queryFn: fetchSlips });
  const { data: week } = useQuery({
    queryKey: ["calendar", today, weekEnd],
    queryFn: () => fetchCalendar(today, weekEnd),
  });

  const toSettle = useMemo(() => needsSettling(slips ?? []), [slips]);
  const todaySlips = useMemo(
    () => (slips ?? []).filter((s) => slipMatchDay(s) === today),
    [slips, today]
  );

  const settledToday = todaySlips.filter((s) => s.result !== "pending");
  const currency = slips?.[0]?.currency ?? "USD";
  const todayPnl = settledToday.reduce((a, s) => a + s.profit_loss, 0);

  const todayCard = week?.days.find((d) => d.date === today);
  const upcoming = week?.days.filter((d) => d.date > today) ?? [];

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[#111827]">
            {dateFromISO(today).toLocaleDateString(undefined, {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}
          </h1>
          <p className="mt-1 text-sm text-[#6B7280]">
            {todayCard
              ? `${todayCard.fixture_count} ${todayCard.fixture_count === 1 ? "match" : "matches"} across ${todayCard.leagues.length} ${todayCard.leagues.length === 1 ? "league" : "leagues"}.`
              : "Today's card."}
          </p>
        </div>
        {settledToday.length > 0 && (
          <div className="text-right">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
              Today
            </p>
            <p
              className={`text-lg font-semibold tabular-nums ${
                todayPnl > 0
                  ? "text-[#059669]"
                  : todayPnl < 0
                    ? "text-[#DC2626]"
                    : "text-[#111827]"
              }`}
            >
              {formatSignedCurrency(todayPnl, currency)}
            </p>
          </div>
        )}
      </div>

      {toSettle.length > 0 && (
        <section className="flex flex-col gap-3">
          <div className="flex items-center gap-2 rounded-xl border border-[#D97706]/25 bg-[#FEF3C7]/60 px-4 py-3">
            <AlertCircle size={16} className="shrink-0 text-[#D97706]" />
            <p className="text-sm text-[#92400E]">
              <span className="font-semibold">
                {toSettle.length} {toSettle.length === 1 ? "slip has" : "slips have"} finished
              </span>{" "}
              and {toSettle.length === 1 ? "is" : "are"} waiting to be settled.
            </p>
            <Link
              href="/slips"
              className="ml-auto flex shrink-0 items-center gap-1 text-sm font-medium text-[#D97706] hover:underline"
            >
              Settle
              <ArrowRight size={14} />
            </Link>
          </div>
          <div className="flex flex-col gap-3">
            {toSettle.slice(0, 2).map((slip) => (
              <SlipCard key={slip.id} slip={slip} />
            ))}
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[#6B7280]">
          Today&apos;s slip
        </h2>
        <DailyAcca date={today} autoLoad />
      </section>

      {todaySlips.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[#6B7280]">
            Placed for today
          </h2>
          <div className="flex flex-col gap-3">
            {todaySlips.map((slip) => (
              <SlipCard key={slip.id} slip={slip} />
            ))}
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[#6B7280]">
            Next 6 days
          </h2>
          <Link
            href="/calendar"
            className="flex items-center gap-1 text-xs font-medium text-[#6C47FF] hover:underline"
          >
            <CalendarDays size={13} />
            Full calendar
          </Link>
        </div>
        <UpcomingStrip days={upcoming} />
      </section>
    </div>
  );
}
