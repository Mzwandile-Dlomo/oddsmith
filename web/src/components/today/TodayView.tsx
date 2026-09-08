"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, CalendarDays, Radio, ScanLine, TrendingUp } from "lucide-react";
import { fetchCalendar, fetchSlips } from "@/lib/api";
import type { CalendarDay, SlipView } from "@/lib/types";
import {
  addDays,
  dateFromISO,
  formatSignedCurrency,
  hasFinished,
  toLocalISODate,
  todayISO,
} from "@/lib/utils";
import { DailyAcca } from "@/components/generator/DailyAcca";
import { SlipCard } from "@/components/slips/SlipCard";
import { SectionHeading } from "@/components/shell/PageHeader";
import { slipMatchDay } from "@/components/calendar/DayView";

/** Pending slips whose last kickoff has passed — these are waiting on you. */
function needsSettling(slips: SlipView[]): SlipView[] {
  const now = Date.now();
  return slips.filter((slip) => {
    if (slip.result !== "pending" || slip.legs.length === 0) return false;
    return slip.legs.every((l) => hasFinished(l.kickoff_utc, now));
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
            className="flex min-w-0 flex-col gap-1 rounded-xl border border-border bg-surface px-3 py-2.5 transition-colors hover:border-accent/40 hover:bg-accent-light/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          >
            <span className="text-[10px] font-semibold uppercase tracking-widest text-faint">
              {d.toLocaleDateString(undefined, { weekday: "short", day: "numeric" })}
            </span>
            <span className="text-sm font-semibold tabular-nums text-ink">
              {day.fixture_count}
              <span className="ml-1 text-[11px] font-normal text-faint">
                {day.fixture_count === 1 ? "match" : "matches"}
              </span>
            </span>
            <span
              className={`truncate text-[11px] font-medium ${
                playable ? "text-success" : "text-faint"
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
      <div className="relative overflow-hidden rounded-2xl border border-border bg-surface px-5 py-6 shadow-panel sm:px-8 sm:py-8">
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full border-[36px] border-accent/10" />
        <div className="relative flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          <div className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-accent">
            <Radio size={12} className="animate-pulse" /> Live market board
          </div>
          <h1 className="max-w-xl text-3xl font-semibold leading-[1.05] tracking-[-0.04em] text-ink sm:text-5xl">
            Find the price<br className="hidden sm:block" /> worth taking.
          </h1>
          <p className="mb-3 text-xs font-medium uppercase tracking-widest text-muted">
            {dateFromISO(today).toLocaleDateString(undefined, {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}
          </p>
          <p className="max-w-md text-sm leading-relaxed text-muted">
            {todayCard
              ? `${todayCard.fixture_count} ${todayCard.fixture_count === 1 ? "match" : "matches"} across ${todayCard.leagues.length} ${todayCard.leagues.length === 1 ? "league" : "leagues"}.`
              : "Today's card."}
          </p>
        </div>
        {settledToday.length > 0 && (
          <div className="shrink-0 sm:text-right">
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-faint">
              Session P&amp;L
            </p>
            <p
              className={`text-lg font-semibold tabular-nums ${
                todayPnl > 0
                  ? "text-success"
                  : todayPnl < 0
                    ? "text-danger"
                    : "text-ink"
              }`}
            >
              {formatSignedCurrency(todayPnl, currency)}
            </p>
          </div>
        )}
        </div>
        <div className="relative mt-7 grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-border bg-border">
          <div className="bg-canvas/70 px-3 py-3 sm:px-4"><p className="text-[10px] uppercase tracking-widest text-faint">Fixtures</p><p className="mt-1 text-xl font-semibold tabular-nums text-ink">{todayCard?.fixture_count ?? 0}</p></div>
          <div className="bg-canvas/70 px-3 py-3 sm:px-4"><p className="text-[10px] uppercase tracking-widest text-faint">Leagues</p><p className="mt-1 text-xl font-semibold tabular-nums text-ink">{todayCard?.leagues.length ?? 0}</p></div>
          <div className="bg-canvas/70 px-3 py-3 sm:px-4"><p className="text-[10px] uppercase tracking-widest text-faint">Signal</p><p className="mt-1 flex items-center gap-1 text-xl font-semibold text-accent"><TrendingUp size={17} /> scan</p></div>
        </div>
      </div>

      {toSettle.length > 0 && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-warn/25 bg-warn-soft/60 px-4 py-3">
            <AlertCircle size={16} className="shrink-0 text-warn" />
            <p className="min-w-0 flex-1 text-sm text-warn-strong">
              <span className="font-semibold">
                {toSettle.length} {toSettle.length === 1 ? "slip has" : "slips have"} finished
              </span>{" "}
              and {toSettle.length === 1 ? "is" : "are"} waiting to be settled.
            </p>
            <Link
              href="/slips"
              className="flex min-h-[40px] shrink-0 items-center gap-1 rounded-lg px-2.5 text-sm font-medium text-warn transition-colors hover:bg-warn-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-warn/40 sm:min-h-[32px]"
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
        <div className="flex items-end justify-between gap-3">
          <div><p className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-accent"><ScanLine size={12} /> Model output</p><SectionHeading title="Today's slip" /></div>
          <span className="hidden text-xs text-faint sm:block">Probability first. Price second.</span>
        </div>
        <DailyAcca date={today} autoLoad autoTrack />
      </section>

      {todaySlips.length > 0 && (
        <section className="flex flex-col gap-3">
          <SectionHeading title="Placed for today" count={todaySlips.length} />
          <div className="grid items-start gap-3 xl:grid-cols-2">
            {todaySlips.map((slip) => (
              <SlipCard key={slip.id} slip={slip} />
            ))}
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <SectionHeading
          title="Next 6 days"
          action={
            <Link
              href="/calendar"
              className="flex min-h-[40px] items-center gap-1 rounded-lg px-2 text-xs font-medium text-accent transition-colors hover:bg-accent-light focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[30px]"
            >
              <CalendarDays size={13} />
              Full calendar
            </Link>
          }
        />
        <UpcomingStrip days={upcoming} />
      </section>
    </div>
  );
}
