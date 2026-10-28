"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Users } from "lucide-react";
import { fetchHistoryMatches, fetchLeagueTable, fetchTeamStats } from "@/lib/api";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/Spinner";
import { MatchRow, TeamStatsPanel } from "@/components/history/HistoryParts";
import { leagueLabel, seasonLabel } from "@/components/leagues/labels";

export function TeamView({ team, league }: { team: string; league: string | null }) {
  // With a league, "this season" comes straight from its table row.
  const table = useQuery({
    queryKey: ["league-table", league, undefined],
    queryFn: () => fetchLeagueTable(league as string),
    enabled: league !== null,
  });
  const seasonRow = table.data?.rows.find((r) => r.team === team);
  const position = seasonRow ? (table.data?.rows.indexOf(seasonRow) ?? -1) + 1 : null;

  // Without one (e.g. linked from a fixture), fall back to all recorded seasons.
  const allTime = useQuery({
    queryKey: ["team-stats", team, league],
    queryFn: () => fetchTeamStats(team, league ?? undefined),
    enabled: league === null || (table.isFetched && !seasonRow),
    retry: false,
  });
  const matches = useQuery({
    queryKey: ["history-matches", league ?? "", team, 20],
    queryFn: () => fetchHistoryMatches(league ?? undefined, team, 20),
  });

  const stats = seasonRow ?? allTime.data;
  const loading = table.isLoading || allTime.isLoading;
  const notFound = !loading && !stats && (allTime.isError || allTime.isFetched);

  return (
    <div className="flex flex-col gap-5">
      <Link
        href={league ? `/leagues?league=${encodeURIComponent(league)}` : "/teams"}
        className="inline-flex min-h-[40px] items-center gap-1.5 self-start rounded-lg text-sm font-medium text-muted transition-colors hover:text-ink"
      >
        <ArrowLeft size={15} />
        {league ? leagueLabel(league) : "Teams"}
      </Link>

      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{team}</h1>
        <p className="mt-1 text-sm text-muted">
          {seasonRow && table.data
            ? `${ordinal(position ?? 0)} in ${leagueLabel(table.data.league)} · ${seasonLabel(table.data.season)}`
            : stats
              ? `All recorded seasons${league ? ` in ${leagueLabel(league)}` : ""}`
              : ""}
        </p>
      </div>

      {loading && <SkeletonCard />}

      {notFound && (
        <EmptyState
          icon={<Users size={22} />}
          title="No history under this name"
          description="Fixture providers sometimes spell clubs differently from the history data (“Manchester City” vs “Man City”). Try the team search."
          action={
            <Link href={`/teams?q=${encodeURIComponent(team.split(" ").slice(-1)[0])}`} className="text-sm font-medium text-accent">
              Search similar names
            </Link>
          }
        />
      )}

      {stats && (
        <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
          <div className="lg:sticky lg:top-20 lg:self-start">
            <TeamStatsPanel stats={stats} />
          </div>
          <section className="flex min-w-0 flex-col gap-3">
            <h2 className="text-base font-semibold text-ink">Recent results</h2>
            {matches.isLoading && <SkeletonCard />}
            {matches.data?.map((match) => (
              <MatchRow key={match.id} match={match} />
            ))}
          </section>
        </div>
      )}
    </div>
  );
}

function ordinal(n: number): string {
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] ?? "th";
  return `${n}${suffix}`;
}
