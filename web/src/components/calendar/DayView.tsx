"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, Trophy } from "lucide-react";
import { fetchCalendar, fetchFixtures, fetchSlips } from "@/lib/api";
import type { SlipView } from "@/lib/types";
import {
  addDays,
  dateFromISO,
  dayLabel,
  formatSignedCurrency,
  toLocalISODate,
  todayISO,
} from "@/lib/utils";
import { FixtureCard } from "@/components/fixtures/FixtureCard";
import { SlipCard } from "@/components/slips/SlipCard";
import { DailyAcca } from "@/components/generator/DailyAcca";
import { SkeletonCard } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Stat, StatGrid, signTone } from "@/components/ui/Stat";
import { SectionHeading } from "@/components/shell/PageHeader";

/**
 * Which day a slip belongs to — its earliest kickoff, matching the backend's
 * `_slip_match_day`. A slip built the night before is a bet on tomorrow's card.
 */
export function slipMatchDay(slip: SlipView): string {
  if (slip.legs.length === 0) return slip.created_at.slice(0, 10);
  const earliest = slip.legs
    .map((l) => l.kickoff_utc)
    .sort((a, b) => a.localeCompare(b))[0];
  return toLocalISODate(new Date(earliest));
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <SectionHeading title={title} count={count} />
      {children}
    </section>
  );
}

export function DayView({ date }: { date: string }) {
  const prev = toLocalISODate(addDays(dateFromISO(date), -1));
  const next = toLocalISODate(addDays(dateFromISO(date), 1));
  const isPast = date < todayISO();

  const { data: summary } = useQuery({
    queryKey: ["calendar", date, date],
    queryFn: () => fetchCalendar(date, date),
  });

  const {
    data: fixtures,
    isLoading: fixturesLoading,
    isError: fixturesError,
  } = useQuery({
    // Past days are review-only: read the cache rather than spending odds-API
    // quota re-fetching a card that has already been played.
    queryKey: ["fixtures", date, date, isPast],
    queryFn: () => fetchFixtures(date, date, isPast),
  });

  const { data: slips } = useQuery({ queryKey: ["slips"], queryFn: fetchSlips });

  const daySlips = useMemo(
    () => (slips ?? []).filter((s) => slipMatchDay(s) === date),
    [slips, date]
  );

  const day = summary?.days[0];
  const currency = slips?.[0]?.currency ?? "USD";
  const settled = daySlips.filter((s) => s.result !== "pending");
  const pnl = settled.reduce((a, s) => a + s.profit_loss, 0);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <div className="flex min-w-0 items-center gap-2">
          <Link
            href="/calendar"
            className="flex min-h-[40px] shrink-0 items-center gap-1 rounded-lg px-2 text-xs font-medium text-accent transition-colors hover:bg-accent-light focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[30px]"
          >
            <CalendarDays size={13} />
            Calendar
          </Link>
          <span className="text-outline">/</span>
          <h1 className="min-w-0 truncate text-lg font-semibold tracking-tight text-ink sm:text-xl">
            {dayLabel(date)}
          </h1>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <Link
            href={`/calendar/${prev}`}
            aria-label="Previous day"
            className="flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-surface text-muted transition-colors hover:bg-hairline hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:h-9 sm:w-9"
          >
            <ChevronLeft size={16} />
          </Link>
          <Link
            href={`/calendar/${next}`}
            aria-label="Next day"
            className="flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-surface text-muted transition-colors hover:bg-hairline hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:h-9 sm:w-9"
          >
            <ChevronRight size={16} />
          </Link>
        </div>
      </div>

      {day && (
        <StatGrid min="8.5rem">
          <Stat label="Matches" value={day.fixture_count} />
          <Stat label="Leagues" value={day.leagues.length} />
          <Stat
            label="Model"
            value={
              day.model?.target_met
                ? `${Math.round(day.model.combined_model_prob * 100)}% @ ${day.model.combined_odds.toFixed(2)}`
                : day.fixture_count === 0
                  ? "—"
                  : "No target slip"
            }
            tone={day.model?.target_met ? "success" : "default"}
          />
          <Stat
            label={settled.length > 0 ? "Settled P&L" : "Slips"}
            value={
              settled.length > 0
                ? formatSignedCurrency(pnl, currency)
                : daySlips.length
            }
            tone={signTone(pnl, settled.length === 0)}
          />
        </StatGrid>
      )}

      {/* A past day's slip cannot be placed any more, so lead with what happened. */}
      {!isPast && (
        <Section title="Slip for this day">
          <DailyAcca date={date} autoLoad />
        </Section>
      )}

      {daySlips.length > 0 && (
        <Section title={isPast ? "Results" : "Your slips"} count={daySlips.length}>
          <div className="flex flex-col gap-3">
            {daySlips.map((slip) => (
              <SlipCard key={slip.id} slip={slip} />
            ))}
          </div>
        </Section>
      )}

      <Section title="Fixtures" count={fixtures?.length}>
        {fixturesLoading && (
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {fixturesError && (
          <div className="rounded-xl border border-danger-line bg-danger-faint px-4 py-3 text-sm text-danger">
            Failed to load fixtures for this day.
          </div>
        )}

        {!fixturesLoading && !fixturesError && fixtures?.length === 0 && (
          <EmptyState
            icon={<Trophy size={22} />}
            title="No matches on this day"
            description="Nothing has been scheduled or fetched for this date yet."
          />
        )}

        {!fixturesLoading && fixtures && fixtures.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-border bg-surface shadow-card">
            <div className="flex flex-col divide-y divide-hairline">
              {fixtures.map((fixture) => (
                <FixtureCard key={fixture.id} fixture={fixture} />
              ))}
            </div>
          </div>
        )}
      </Section>
    </div>
  );
}

