"use client";

import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Search, Users } from "lucide-react";
import { fetchLeagueTable } from "@/lib/api";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/Spinner";
import { MAIN_LEAGUES, seasonLabel } from "@/components/leagues/labels";

/** Normalized for matching: "Mönchengladbach" finds "Monchengladbach" too. */
function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function TeamsView({ initialQuery }: { initialQuery: string }) {
  const [query, setQuery] = useState(initialQuery);
  const needle = fold(useDeferredValue(query.trim()));

  // Same keys as the Leagues page, so a table loaded there is reused here.
  const tables = useQueries({
    queries: MAIN_LEAGUES.map((l) => ({
      queryKey: ["league-table", l.key, undefined],
      queryFn: () => fetchLeagueTable(l.key),
    })),
  });
  const loading = tables.some((t) => t.isLoading);

  const groups = MAIN_LEAGUES.map((league, i) => {
    const data = tables[i].data;
    const rows = (data?.rows ?? [])
      .map((row, position) => ({ row, position: position + 1 }))
      .filter(({ row }) => !needle || fold(row.team).includes(needle));
    return { league, season: data?.season, rows };
  }).filter((g) => g.rows.length > 0);

  return (
    <div className="flex flex-col gap-6">
      <div className="relative max-w-md">
        <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
        <label htmlFor="team-filter" className="sr-only">
          Filter teams
        </label>
        <input
          id="team-filter"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter teams (e.g. Arsenal)…"
          className="min-h-[44px] w-full rounded-xl border border-border bg-surface pl-9 pr-4 text-base text-ink placeholder:text-faint focus:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/20 sm:min-h-[38px] sm:text-sm"
        />
      </div>

      {loading && <SkeletonCard />}

      {!loading && groups.length === 0 && (
        <EmptyState
          icon={<Users size={22} />}
          title="No teams match"
          description={`Nothing in the five leagues matches "${query.trim()}". Club names follow the history data, e.g. "Man City".`}
        />
      )}

      {groups.map(({ league, season, rows }) => (
        <section key={league.key} className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-ink">
            {league.label}
            {season !== undefined && <span className="ml-2 font-normal text-faint">{seasonLabel(season)}</span>}
          </h2>
          <div className="grid grid-cols-1 gap-2 min-[480px]:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
            {rows.map(({ row, position }) => (
              <Link
                key={row.team}
                href={`/teams/${encodeURIComponent(row.team)}?league=${encodeURIComponent(league.key)}`}
                className="flex min-w-0 items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3 transition-colors hover:border-accent/40 hover:bg-accent-light/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
              >
                <span className="w-6 shrink-0 text-right text-xs tabular-nums text-faint">{position}</span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{row.team}</span>
                <span className="shrink-0 text-xs tabular-nums text-muted">{row.points} pts</span>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
