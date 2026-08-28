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
      <div className="flex items-baseline gap-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[#6B7280]">
          {title}
        </h2>
        {count !== undefined && (
          <span className="text-[11px] tabular-nums text-[#9CA3AF]">{count}</span>
        )}
      </div>
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link
            href="/calendar"
            className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-[#6C47FF] transition-colors hover:bg-[#EEE9FF]"
          >
            <CalendarDays size={13} />
            Calendar
          </Link>
          <span className="text-[#D1D5DB]">/</span>
          <h1 className="text-xl font-semibold tracking-tight text-[#111827]">
            {dayLabel(date)}
          </h1>
        </div>

        <div className="flex items-center gap-1">
          <Link
            href={`/calendar/${prev}`}
            aria-label="Previous day"
            className="rounded-lg border border-[#E5E7EB] bg-white p-1.5 text-[#6B7280] transition-colors hover:bg-[#F3F4F6] hover:text-[#111827]"
          >
            <ChevronLeft size={16} />
          </Link>
          <Link
            href={`/calendar/${next}`}
            aria-label="Next day"
            className="rounded-lg border border-[#E5E7EB] bg-white p-1.5 text-[#6B7280] transition-colors hover:bg-[#F3F4F6] hover:text-[#111827]"
          >
            <ChevronRight size={16} />
          </Link>
        </div>
      </div>

      {day && (
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-[#E5E7EB] bg-[#F3F4F6] shadow-[0_1px_3px_rgba(0,0,0,0.06)] sm:grid-cols-4">
          <Tile label="Matches" value={String(day.fixture_count)} />
          <Tile label="Leagues" value={String(day.leagues.length)} />
          <Tile
            label="Model"
            value={
              day.model?.target_met
                ? `${Math.round(day.model.combined_model_prob * 100)}% @ ${day.model.combined_odds.toFixed(2)}`
                : day.fixture_count === 0
                  ? "—"
                  : "No target slip"
            }
            tone={day.model?.target_met ? "text-[#059669]" : undefined}
          />
          <Tile
            label={settled.length > 0 ? "Settled P&L" : "Slips"}
            value={
              settled.length > 0
                ? formatSignedCurrency(pnl, currency)
                : `${daySlips.length}`
            }
            tone={
              settled.length === 0
                ? undefined
                : pnl > 0
                  ? "text-[#059669]"
                  : pnl < 0
                    ? "text-[#DC2626]"
                    : undefined
            }
          />
        </div>
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
          <div className="rounded-xl border border-[#FEE2E2] bg-[#FEE2E2]/50 px-4 py-3 text-sm text-[#DC2626]">
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
          <div className="overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
            <div className="flex flex-col divide-y divide-[#F3F4F6]">
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

function Tile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="bg-white px-4 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
        {label}
      </p>
      <p className={`mt-1 text-base font-semibold tabular-nums ${tone ?? "text-[#111827]"}`}>
        {value}
      </p>
    </div>
  );
}
