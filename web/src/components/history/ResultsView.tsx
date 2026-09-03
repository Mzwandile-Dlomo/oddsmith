"use client";

import { useState, useDeferredValue } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Trophy, TrendingUp } from "lucide-react";
import { fetchHistoryLeagues, fetchHistoryMatches, fetchTeamStats } from "@/lib/api";
import type { HistoryMatch, TeamStatsView } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SpinnerOverlay, SkeletonCard } from "@/components/ui/Spinner";

function FormChip({ result }: { result: string }) {
  const colorMap: Record<string, string> = {
    W: "bg-success text-white",
    D: "bg-warn text-white",
    L: "bg-danger text-white",
  };
  const cls = colorMap[result] ?? "bg-border text-muted";
  return (
    <span
      className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold ${cls}`}
    >
      {result}
    </span>
  );
}

function MatchRow({ match }: { match: HistoryMatch }) {
  const homeWon = match.home_goals > match.away_goals;
  const awayWon = match.away_goals > match.home_goals;
  const date = new Date(match.kickoff_utc).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  return (
    /*
      Phones get a two-row layout: names on their own line with the score, then
      the date beneath. Squeezing name/score/name/date onto one line left each
      club roughly 74px at 375px, which cut most real names in half.
    */
    <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-surface px-4 py-3 shadow-subtle sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
        <span
          className={`truncate text-sm ${homeWon ? "font-semibold text-ink" : "font-normal text-muted"}`}
        >
          {match.home_team}
        </span>
        <div className="flex shrink-0 items-center gap-1.5">
          <span
            className={`text-base tabular-nums ${homeWon ? "font-bold text-ink" : "font-semibold text-muted"}`}
          >
            {match.home_goals}
          </span>
          <span className="text-xs font-medium text-faint">–</span>
          <span
            className={`text-base tabular-nums ${awayWon ? "font-bold text-ink" : "font-semibold text-muted"}`}
          >
            {match.away_goals}
          </span>
        </div>
        <span
          className={`truncate text-right text-sm ${awayWon ? "font-semibold text-ink" : "font-normal text-muted"}`}
        >
          {match.away_team}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-2 text-[11px] sm:flex-col sm:items-end sm:gap-0.5">
        <span className="text-faint">{date}</span>
        {/* Was `text-accent-mid` (violet-300) on white — about 1.9:1, well under AA. */}
        <span className="text-muted">Season {match.season}</span>
      </div>
    </div>
  );
}

function TeamStatsPanel({
  stats,
}: {
  stats: TeamStatsView;
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-2">
        <Trophy className="h-4 w-4 text-accent" />
        <h3 className="text-sm font-semibold text-ink">{stats.team}</h3>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2 min-[380px]:grid-cols-4 sm:gap-3">
        {(
          [
            { label: "Played", value: stats.played },
            { label: "Won", value: stats.won },
            { label: "Drawn", value: stats.drawn },
            { label: "Lost", value: stats.lost },
          ] as const
        ).map(({ label, value }) => (
          <div
            key={label}
            className="flex min-w-0 flex-col items-center rounded-xl bg-subtle px-2 py-3"
          >
            <span className="text-lg font-bold text-ink">{value}</span>
            <span className="text-[11px] text-faint">{label}</span>
          </div>
        ))}
      </div>

      <div className="mb-4 grid grid-cols-3 gap-2 sm:gap-3">
        <div className="flex min-w-0 flex-col items-center rounded-xl bg-accent-light px-2 py-3">
          <span className="text-lg font-bold text-accent">{stats.points}</span>
          <span className="text-[11px] text-accent/70">Points</span>
        </div>
        <div className="flex min-w-0 flex-col items-center rounded-xl bg-subtle px-2 py-3">
          <span className="text-lg font-bold text-ink">
            {stats.goals_for}/{stats.goals_against}
          </span>
          <span className="text-[11px] text-faint">GF/GA</span>
        </div>
        <div className="flex min-w-0 flex-col items-center rounded-xl bg-subtle px-2 py-3">
          <span
            className={`text-lg font-bold ${stats.goal_difference >= 0 ? "text-success" : "text-danger"}`}
          >
            {stats.goal_difference >= 0 ? "+" : ""}
            {stats.goal_difference}
          </span>
          <span className="text-[11px] text-faint">GD</span>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2 sm:gap-3">
        <div className="rounded-xl border border-border px-3 py-2">
          <span className="block text-[11px] font-medium text-faint">Home</span>
          <span className="text-sm font-semibold text-ink">{stats.home_record}</span>
        </div>
        <div className="rounded-xl border border-border px-3 py-2">
          <span className="block text-[11px] font-medium text-faint">Away</span>
          <span className="text-sm font-semibold text-ink">{stats.away_record}</span>
        </div>
      </div>

      <div>
        <span className="mb-2 block text-[11px] font-medium uppercase tracking-wider text-faint">
          Form
        </span>
        <div className="flex flex-wrap gap-1.5">
          {stats.form.map((result, i) => (
            <FormChip key={i} result={result} />
          ))}
        </div>
      </div>
    </Card>
  );
}

export function ResultsView() {
  const [selectedLeague, setSelectedLeague] = useState<string | null>(null);
  const [teamSearch, setTeamSearch] = useState("");
  const deferredTeamSearch = useDeferredValue(teamSearch.trim());

  const {
    data: leagues,
    isLoading: leaguesLoading,
    isError: leaguesError,
  } = useQuery({
    queryKey: ["history-leagues"],
    queryFn: fetchHistoryLeagues,
  });

  const activeLeague = selectedLeague ?? leagues?.[0] ?? null;

  const {
    data: matches,
    isLoading: matchesLoading,
    isError: matchesError,
  } = useQuery({
    queryKey: ["history-matches", activeLeague, deferredTeamSearch],
    queryFn: () =>
      fetchHistoryMatches(
        activeLeague ?? undefined,
        deferredTeamSearch || undefined
      ),
    enabled: activeLeague !== null,
  });

  const {
    data: teamStats,
    isLoading: statsLoading,
    isError: statsError,
  } = useQuery({
    queryKey: ["team-stats", deferredTeamSearch, activeLeague],
    queryFn: () =>
      fetchTeamStats(deferredTeamSearch, activeLeague ?? undefined),
    enabled: deferredTeamSearch.length >= 2,
  });

  return (
    <div className="space-y-6">
      {/* One scrolling row on phones instead of four ragged wrapped lines. */}
      <div className="scroll-x -mx-4 flex items-center gap-2 px-4 sm:mx-0 sm:flex-wrap sm:px-0">
        {leaguesLoading && (
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="h-8 w-20 animate-pulse rounded-full bg-hairline"
              />
            ))}
          </div>
        )}
        {leaguesError && (
          <p className="text-sm text-danger">Failed to load leagues.</p>
        )}
        {leagues?.map((league) => {
          const isActive = league === activeLeague;
          return (
            <button
              key={league}
              onClick={() => setSelectedLeague(league)}
              aria-pressed={isActive}
              className={`flex min-h-[44px] shrink-0 items-center whitespace-nowrap rounded-full border px-4 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[34px] ${
                isActive
                  ? "border-accent bg-accent text-white"
                  : "border-border bg-surface text-muted hover:border-accent/40 hover:text-accent"
              }`}
            >
              {league}
            </button>
          );
        })}
      </div>

      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
        <label className="sr-only" htmlFor="team-search">
          Search team
        </label>
        <input
          id="team-search"
          type="search"
          placeholder="Search team (e.g. Arsenal)…"
          value={teamSearch}
          onChange={(e) => setTeamSearch(e.target.value)}
          className="min-h-[44px] w-full rounded-xl border border-border bg-surface pl-9 pr-4 text-base text-ink placeholder:text-faint focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 sm:min-h-[38px] sm:text-sm"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-2">
          {matchesLoading && (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <SkeletonCard key={i} />
              ))}
            </div>
          )}
          {matchesError && (
            <EmptyState
              icon={<TrendingUp className="h-5 w-5" />}
              title="Failed to load results"
              description="Could not connect to the history API. Make sure the backend is running."
            />
          )}
          {!matchesLoading && !matchesError && matches?.length === 0 && (
            <EmptyState
              icon={<TrendingUp className="h-5 w-5" />}
              title="No results found"
              description={
                deferredTeamSearch
                  ? `No matches found for "${deferredTeamSearch}" in ${activeLeague ?? "this league"}.`
                  : `No past results for ${activeLeague ?? "this league"} yet.`
              }
            />
          )}
          {!matchesLoading &&
            matches?.map((match) => <MatchRow key={match.id} match={match} />)}
        </div>

        <div className="lg:sticky lg:top-6 lg:max-h-[calc(100dvh-3rem)] lg:self-start lg:overflow-y-auto lg:overscroll-contain">
          {statsLoading && deferredTeamSearch.length >= 2 && (
            <SpinnerOverlay label={`Loading stats for ${deferredTeamSearch}…`} />
          )}
          {statsError && deferredTeamSearch.length >= 2 && (
            <EmptyState
              icon={<Trophy className="h-5 w-5" />}
              title="Stats not found"
              description={`No stats found for "${deferredTeamSearch}". Try the exact team name.`}
            />
          )}
          {!statsLoading && !statsError && teamStats && (
            <TeamStatsPanel stats={teamStats} />
          )}
          {!deferredTeamSearch && (
            <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border bg-surface px-6 py-12 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-light text-accent">
                <Trophy className="h-5 w-5" />
              </div>
              <p className="text-sm font-semibold text-ink">Team Stats</p>
              <p className="max-w-[200px] text-xs text-faint">
                Search for a team above to see its stats and form.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
