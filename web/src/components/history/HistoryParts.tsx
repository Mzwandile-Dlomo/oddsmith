"use client";

import { Trophy } from "lucide-react";
import type { HistoryMatch, TeamStatsView } from "@/lib/types";
import { parseKickoff } from "@/lib/utils";
import { Card } from "@/components/ui/Card";

export function FormChip({ result }: { result: string }) {
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

export function MatchRow({ match }: { match: HistoryMatch }) {
  const homeWon = match.home_goals > match.away_goals;
  const awayWon = match.away_goals > match.home_goals;
  const date = parseKickoff(match.kickoff_utc).toLocaleDateString("en-GB", {
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

export function TeamStatsPanel({
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
