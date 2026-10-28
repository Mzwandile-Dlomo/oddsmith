"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarX, Clock, Trophy } from "lucide-react";
import { fetchFixtures } from "@/lib/api";
import type { Fixture, ModelOutcome } from "@/lib/types";
import { formatKickoff, formatOdds, formatPercent, legLabel, todayISO } from "@/lib/utils";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { SkeletonCard } from "@/components/ui/Spinner";
import { FixtureInsights } from "@/components/fixtures/FixtureInsights";
import { MarketPicker } from "@/components/fixtures/MarketPicker";
import { SlipDock } from "@/components/slip/SlipDock";

function ProbabilityRow({ outcome, fixture }: { outcome: ModelOutcome; fixture: Fixture }) {
  const label = legLabel("match_winner", outcome.name, null, fixture.home_team, fixture.away_team);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="truncate text-sm font-medium text-ink">{label}</span>
        <span className="shrink-0 text-sm font-semibold tabular-nums text-ink">
          {formatPercent(outcome.model_prob)}
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-hairline"
        role="img"
        aria-label={`Model probability ${formatPercent(outcome.model_prob)}`}
      >
        <div
          className="h-full rounded-full bg-accent-mid"
          style={{ width: `${Math.min(outcome.model_prob, 1) * 100}%` }}
        />
      </div>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
        <span>
          Fair <span className="tabular-nums text-ink-soft">{formatOdds(outcome.model_odds)}</span>
        </span>
        <span>
          Bookmaker{" "}
          <span className="tabular-nums text-ink-soft">
            {outcome.bookmaker_odds === null ? "—" : formatOdds(outcome.bookmaker_odds)}
          </span>
        </span>
        {outcome.is_value && outcome.edge !== null && (
          <span className="rounded-full bg-accent-light px-1.5 py-0.5 text-[10px] font-semibold text-accent">
            Value +{Math.round(outcome.edge * 100)}%
          </span>
        )}
      </p>
    </div>
  );
}

/** The model's 1X2 read next to the price, so the "is this worth it" answer comes first. */
function ModelSummary({ fixture }: { fixture: Fixture }) {
  const winner = fixture.model_markets.find((m) => m.type === "match_winner");
  return (
    <section className="rounded-2xl border border-border bg-surface p-5 shadow-card">
      <h2 className="text-sm font-semibold text-ink">Model prediction</h2>
      {winner ? (
        <div className="mt-4 flex flex-col gap-4">
          {winner.outcomes.map((outcome) => (
            <ProbabilityRow key={outcome.name} outcome={outcome} fixture={fixture} />
          ))}
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted">
          No model prediction for this match yet — it needs both teams in the model&apos;s
          league history.
        </p>
      )}
    </section>
  );
}

export function MatchView({ id, date }: { id: string; date: string | null }) {
  const [view, setView] = useState<"markets" | "insights">("markets");
  // A past day is read from the cache only, so reviewing it never spends quota.
  const cachedOnly = date !== null && date < todayISO();

  const { data: fixtures, isLoading, isError, error } = useQuery({
    queryKey: ["fixtures", date, date, cachedOnly],
    queryFn: () => fetchFixtures(date ?? undefined, date ?? undefined, cachedOnly),
    enabled: date !== null,
  });
  const fixture = fixtures?.find((f) => f.id === id);

  const back = (
    <Link
      href="/matches"
      className="inline-flex min-h-[40px] items-center gap-1.5 rounded-lg text-sm font-medium text-muted transition-colors hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
    >
      <ArrowLeft size={15} />
      Matches
    </Link>
  );

  if (date === null || (!isLoading && !isError && !fixture)) {
    return (
      <div className="flex flex-col gap-4">
        {back}
        <EmptyState
          icon={<CalendarX size={22} />}
          title="Match not found"
          description="It may have been rescheduled or dropped from the provider's window. Open it again from the match list."
        />
      </div>
    );
  }

  return (
    <SlipDock>
      <div className="flex flex-col gap-5">
        {back}
        {isLoading && <SkeletonCard />}
        {isError && (
          <div className="rounded-xl border border-danger-line bg-danger-faint px-4 py-3 text-sm text-danger">
            {error instanceof Error ? error.message : "Failed to load the match."}
          </div>
        )}
        {fixture && (
          <>
            <header className="rounded-2xl border border-border bg-surface px-5 py-6 shadow-panel sm:px-6">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
                {fixture.league && (
                  <span className="flex items-center gap-1.5">
                    <Trophy size={12} className="text-accent" />
                    {fixture.league}
                  </span>
                )}
                <span className="flex items-center gap-1.5">
                  <Clock size={12} />
                  {formatKickoff(fixture.kickoff_utc)}
                </span>
              </div>
              <h1 className="mt-3 flex flex-col gap-1 text-xl font-semibold tracking-tight text-ink sm:flex-row sm:items-center sm:gap-3 sm:text-2xl">
                <Link href={`/teams/${encodeURIComponent(fixture.home_team)}`} className="hover:text-accent">
                  {fixture.home_team}
                </Link>
                <span className="text-sm font-medium text-faint">vs</span>
                <Link href={`/teams/${encodeURIComponent(fixture.away_team)}`} className="hover:text-accent">
                  {fixture.away_team}
                </Link>
              </h1>
            </header>

            <ModelSummary fixture={fixture} />

            <section className="flex flex-col gap-3">
              <SegmentedControl
                label="Match view"
                value={view}
                onChange={setView}
                segments={[
                  { value: "markets", label: "Markets" },
                  { value: "insights", label: "Form & stats" },
                ]}
              />
              <div className="rounded-2xl border border-border bg-surface p-4 shadow-card">
                {view === "markets" ? (
                  <MarketPicker fixture={fixture} />
                ) : (
                  <FixtureInsights fixture={fixture} />
                )}
              </div>
            </section>
          </>
        )}
      </div>
    </SlipDock>
  );
}
