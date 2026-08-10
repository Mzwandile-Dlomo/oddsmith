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
    W: "bg-[#059669] text-white",
    D: "bg-[#D97706] text-white",
    L: "bg-[#DC2626] text-white",
  };
  const cls = colorMap[result] ?? "bg-[#E5E7EB] text-[#6B7280]";
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
    <div className="flex items-center justify-between gap-4 rounded-xl border border-[#E5E7EB] bg-white px-4 py-3 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
        <span
          className={`truncate text-sm ${homeWon ? "font-semibold text-[#111827]" : "font-normal text-[#6B7280]"}`}
        >
          {match.home_team}
        </span>
        <div className="flex shrink-0 items-center gap-1.5">
          <span
            className={`text-base tabular-nums ${homeWon ? "font-bold text-[#111827]" : "font-semibold text-[#6B7280]"}`}
          >
            {match.home_goals}
          </span>
          <span className="text-xs font-medium text-[#9CA3AF]">–</span>
          <span
            className={`text-base tabular-nums ${awayWon ? "font-bold text-[#111827]" : "font-semibold text-[#6B7280]"}`}
          >
            {match.away_goals}
          </span>
        </div>
        <span
          className={`truncate text-right text-sm ${awayWon ? "font-semibold text-[#111827]" : "font-normal text-[#6B7280]"}`}
        >
          {match.away_team}
        </span>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-0.5">
        <span className="text-[11px] text-[#9CA3AF]">{date}</span>
        <span className="text-[11px] text-[#C4B5FD]">Season {match.season}</span>
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
        <Trophy className="h-4 w-4 text-[#6C47FF]" />
        <h3 className="text-sm font-semibold text-[#111827]">{stats.team}</h3>
      </div>

      <div className="mb-4 grid grid-cols-4 gap-3">
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
            className="flex flex-col items-center rounded-xl bg-[#F9FAFB] px-2 py-3"
          >
            <span className="text-lg font-bold text-[#111827]">{value}</span>
            <span className="text-[11px] text-[#9CA3AF]">{label}</span>
          </div>
        ))}
      </div>

      <div className="mb-4 grid grid-cols-3 gap-3">
        <div className="flex flex-col items-center rounded-xl bg-[#EEE9FF] px-2 py-3">
          <span className="text-lg font-bold text-[#6C47FF]">{stats.points}</span>
          <span className="text-[11px] text-[#6C47FF]/70">Points</span>
        </div>
        <div className="flex flex-col items-center rounded-xl bg-[#F9FAFB] px-2 py-3">
          <span className="text-lg font-bold text-[#111827]">
            {stats.goals_for}/{stats.goals_against}
          </span>
          <span className="text-[11px] text-[#9CA3AF]">GF/GA</span>
        </div>
        <div className="flex flex-col items-center rounded-xl bg-[#F9FAFB] px-2 py-3">
          <span
            className={`text-lg font-bold ${stats.goal_difference >= 0 ? "text-[#059669]" : "text-[#DC2626]"}`}
          >
            {stats.goal_difference >= 0 ? "+" : ""}
            {stats.goal_difference}
          </span>
          <span className="text-[11px] text-[#9CA3AF]">GD</span>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-[#E5E7EB] px-3 py-2">
          <span className="block text-[11px] font-medium text-[#9CA3AF]">Home</span>
          <span className="text-sm font-semibold text-[#111827]">{stats.home_record}</span>
        </div>
        <div className="rounded-xl border border-[#E5E7EB] px-3 py-2">
          <span className="block text-[11px] font-medium text-[#9CA3AF]">Away</span>
          <span className="text-sm font-semibold text-[#111827]">{stats.away_record}</span>
        </div>
      </div>

      <div>
        <span className="mb-2 block text-[11px] font-medium uppercase tracking-wider text-[#9CA3AF]">
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
      <div className="flex flex-wrap items-center gap-2">
        {leaguesLoading && (
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="h-8 w-20 animate-pulse rounded-full bg-[#F3F4F6]"
              />
            ))}
          </div>
        )}
        {leaguesError && (
          <p className="text-sm text-[#DC2626]">Failed to load leagues.</p>
        )}
        {leagues?.map((league) => {
          const isActive = league === activeLeague;
          return (
            <button
              key={league}
              onClick={() => setSelectedLeague(league)}
              className={`rounded-full border px-4 py-1.5 text-sm font-medium transition-colors duration-150 ${
                isActive
                  ? "border-[#6C47FF] bg-[#6C47FF] text-white"
                  : "border-[#E5E7EB] bg-white text-[#6B7280] hover:border-[#6C47FF]/40 hover:text-[#6C47FF]"
              }`}
            >
              {league}
            </button>
          );
        })}
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
        <input
          type="text"
          placeholder="Search team (e.g. Arsenal)…"
          value={teamSearch}
          onChange={(e) => setTeamSearch(e.target.value)}
          className="w-full rounded-xl border border-[#E5E7EB] bg-white py-2 pl-9 pr-4 text-sm text-[#111827] placeholder:text-[#9CA3AF] focus:border-[#6C47FF] focus:outline-none focus:ring-2 focus:ring-[#6C47FF]/20"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-2">
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

        <div className="lg:sticky lg:top-[88px] lg:self-start">
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
            <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-[#E5E7EB] bg-white px-6 py-12 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#EEE9FF] text-[#6C47FF]">
                <Trophy className="h-5 w-5" />
              </div>
              <p className="text-sm font-semibold text-[#111827]">Team Stats</p>
              <p className="max-w-[200px] text-xs text-[#9CA3AF]">
                Search for a team above to see its stats and form.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
