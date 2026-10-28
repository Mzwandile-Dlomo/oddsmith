"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Trophy } from "lucide-react";
import { fetchHistoryLeagues, fetchHistoryMatches, fetchLeagueTable } from "@/lib/api";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/Spinner";
import { FormChip, MatchRow } from "@/components/history/HistoryParts";
import { MAIN_LEAGUES, leagueLabel, seasonLabel } from "./labels";

function LeagueChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`flex min-h-[44px] shrink-0 items-center whitespace-nowrap rounded-full border px-4 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[34px] ${
        active
          ? "border-accent/40 bg-accent-light text-accent"
          : "border-border bg-surface text-muted hover:border-accent/40 hover:text-ink"
      }`}
    >
      {label}
    </button>
  );
}

export function LeaguesView({ initialLeague }: { initialLeague: string }) {
  const [league, setLeague] = useState(initialLeague);
  const [season, setSeason] = useState<number | undefined>(undefined);

  const { data: allLeagues } = useQuery({
    queryKey: ["history-leagues"],
    queryFn: fetchHistoryLeagues,
  });
  const table = useQuery({
    queryKey: ["league-table", league, season],
    queryFn: () => fetchLeagueTable(league, season),
  });
  const results = useQuery({
    queryKey: ["history-matches", league, "", 10],
    queryFn: () => fetchHistoryMatches(league, undefined, 10),
  });

  // API-Football's names for the big five ("Premier League", "Serie A") hold a
  // few recent duplicates of rows already under the main keys; hide them.
  const mainNames = new Set(MAIN_LEAGUES.flatMap((l) => [l.key, l.label]));
  const others = (allLeagues ?? []).filter((l) => !mainNames.has(l));

  function pick(next: string) {
    setLeague(next);
    setSeason(undefined);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="scroll-x -mx-4 flex items-center gap-2 px-4 sm:mx-0 sm:flex-wrap sm:px-0">
        {MAIN_LEAGUES.map((l) => (
          <LeagueChip key={l.key} label={l.label} active={league === l.key} onClick={() => pick(l.key)} />
        ))}
        {others.length > 0 && <span className="mx-1 h-5 w-px shrink-0 bg-border" aria-hidden />}
        {others.map((l) => (
          <LeagueChip key={l} label={l} active={league === l} onClick={() => pick(l)} />
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="min-w-0 rounded-2xl border border-border bg-surface shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
            <h2 className="text-base font-semibold text-ink">{leagueLabel(league)} table</h2>
            {table.data && table.data.seasons.length > 1 && (
              <label className="flex items-center gap-2 text-sm text-muted">
                Season
                <select
                  value={table.data.season}
                  onChange={(e) => setSeason(Number(e.target.value))}
                  className="min-h-[40px] rounded-lg border border-border bg-subtle px-2 text-sm text-ink focus:border-accent/60 focus:outline-none sm:min-h-[32px]"
                >
                  {table.data.seasons.map((s) => (
                    <option key={s} value={s}>
                      {seasonLabel(s)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {table.isLoading && (
            <div className="p-5">
              <SkeletonCard />
            </div>
          )}
          {table.isError && (
            <div className="p-5">
              <EmptyState
                icon={<Trophy size={22} />}
                title="No table for this competition"
                description="There are no stored results for it yet."
              />
            </div>
          )}
          {table.data && (
            <div className="scroll-x">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-faint">
                    <th className="w-10 px-3 py-2.5 text-right font-medium">#</th>
                    <th className="px-3 py-2.5 font-medium">Team</th>
                    <th className="px-2 py-2.5 text-right font-medium">P</th>
                    <th className="hidden px-2 py-2.5 text-right font-medium sm:table-cell">W</th>
                    <th className="hidden px-2 py-2.5 text-right font-medium sm:table-cell">D</th>
                    <th className="hidden px-2 py-2.5 text-right font-medium sm:table-cell">L</th>
                    <th className="hidden px-2 py-2.5 text-right font-medium md:table-cell">GF</th>
                    <th className="hidden px-2 py-2.5 text-right font-medium md:table-cell">GA</th>
                    <th className="px-2 py-2.5 text-right font-medium">GD</th>
                    <th className="px-3 py-2.5 text-right font-medium">Pts</th>
                    <th className="hidden px-3 py-2.5 font-medium lg:table-cell">Form</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {table.data.rows.map((row, i) => (
                    <tr key={row.team} className="border-t border-hairline hover:bg-subtle/60">
                      <td className="px-3 py-2.5 text-right text-faint">{i + 1}</td>
                      <td className="max-w-[12rem] truncate px-3 py-2.5">
                        <Link
                          href={`/teams/${encodeURIComponent(row.team)}?league=${encodeURIComponent(league)}`}
                          className="font-medium text-ink hover:text-accent"
                        >
                          {row.team}
                        </Link>
                      </td>
                      <td className="px-2 py-2.5 text-right text-muted">{row.played}</td>
                      <td className="hidden px-2 py-2.5 text-right text-muted sm:table-cell">{row.won}</td>
                      <td className="hidden px-2 py-2.5 text-right text-muted sm:table-cell">{row.drawn}</td>
                      <td className="hidden px-2 py-2.5 text-right text-muted sm:table-cell">{row.lost}</td>
                      <td className="hidden px-2 py-2.5 text-right text-muted md:table-cell">{row.goals_for}</td>
                      <td className="hidden px-2 py-2.5 text-right text-muted md:table-cell">{row.goals_against}</td>
                      <td className="px-2 py-2.5 text-right text-muted">
                        {row.goal_difference > 0 ? "+" : ""}
                        {row.goal_difference}
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold text-ink">{row.points}</td>
                      <td className="hidden px-3 py-2.5 lg:table-cell">
                        <span className="flex gap-1">
                          {row.form.map((r, k) => (
                            <FormChip key={k} result={r} />
                          ))}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="flex min-w-0 flex-col gap-3">
          <h2 className="text-base font-semibold text-ink">Latest results</h2>
          {results.isLoading && <SkeletonCard />}
          {results.data?.map((match) => (
            <MatchRow key={match.id} match={match} />
          ))}
          {results.data?.length === 0 && <p className="text-sm text-muted">No results stored yet.</p>}
        </section>
      </div>
    </div>
  );
}
