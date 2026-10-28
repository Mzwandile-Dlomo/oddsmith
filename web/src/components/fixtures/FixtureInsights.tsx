"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import type { Fixture, LineCount, MatchInsights, TeamAverages, TeamForm, TeamMatch } from "@/lib/types";
import { fetchFixtureInsights } from "@/lib/api";
import { formatOdds, formatPercent } from "@/lib/utils";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Spinner } from "@/components/ui/Spinner";
import { Stat, StatGrid } from "@/components/ui/Stat";

const SAMPLE_SIZES = [5, 10] as const;

function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function formatAverage(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

function pair(a: number | null, b: number | null): string {
  return a === null || b === null ? "—" : `${a}–${b}`;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-faint">{children}</p>
  );
}

/** "4/5" with a bar, so a 5/5 and a 14/15 read as different strengths of evidence. */
function HitCell({ line }: { line: LineCount }) {
  if (line.sample === 0) return <span className="text-faint">—</span>;
  const rate = line.hits / line.sample;
  return (
    <span className="inline-flex min-w-[3.25rem] flex-col gap-0.5">
      <span className="tabular-nums text-ink">
        {line.hits}/{line.sample}
      </span>
      <span className="h-1 w-full overflow-hidden rounded-full bg-hairline">
        <span className="block h-full rounded-full bg-accent-mid" style={{ width: `${rate * 100}%` }} />
      </span>
    </span>
  );
}

const resultChip: Record<TeamMatch["result"], string> = {
  W: "bg-success-soft text-success",
  D: "bg-hairline text-muted",
  L: "bg-danger-soft text-danger",
};

function FormChips({ matches }: { matches: TeamMatch[] }) {
  return (
    <span className="flex gap-1" aria-label="Form, latest first">
      {matches.map((m) => (
        <span
          key={m.kickoff_utc}
          className={`flex h-5 w-5 items-center justify-center rounded text-[10px] font-bold ${resultChip[m.result]}`}
        >
          {m.result}
        </span>
      ))}
    </span>
  );
}

function AverageTiles({ averages }: { averages: TeamAverages }) {
  return (
    <StatGrid min="6.5rem">
      <Stat
        size="sm"
        label="Goals for / ag."
        value={`${formatAverage(averages.goals_for)} / ${formatAverage(averages.goals_against)}`}
        detail={`match total ${formatAverage(averages.total_goals)}`}
      />
      <Stat
        size="sm"
        label="Corners for / ag."
        value={`${formatAverage(averages.corners_for)} / ${formatAverage(averages.corners_against)}`}
        detail={`match total ${formatAverage(averages.total_corners)}`}
      />
      <Stat
        size="sm"
        label="SOT for / ag."
        value={`${formatAverage(averages.shots_on_target_for)} / ${formatAverage(averages.shots_on_target_against)}`}
        detail={`shots ${formatAverage(averages.shots_for)}`}
      />
    </StatGrid>
  );
}

function MatchTable({ matches }: { matches: TeamMatch[] }) {
  return (
    <div className="scroll-x">
      <table className="w-full min-w-[22rem] text-left text-xs">
        <thead className="text-[10px] uppercase tracking-wider text-faint">
          <tr>
            <th className="py-1.5 pr-2 font-semibold">Date</th>
            <th className="py-1.5 pr-2 font-semibold">Opponent</th>
            <th className="py-1.5 pr-2 font-semibold">Score</th>
            <th className="py-1.5 pr-2 font-semibold">Goals</th>
            <th className="py-1.5 pr-2 font-semibold">Corners</th>
            <th className="py-1.5 font-semibold">SOT</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline tabular-nums text-muted-strong">
          {matches.map((m) => (
            <tr key={m.kickoff_utc}>
              <td className="py-1.5 pr-2 whitespace-nowrap text-faint">{formatDay(m.kickoff_utc)}</td>
              <td className="max-w-[9rem] truncate py-1.5 pr-2 text-ink" title={m.league}>
                <span className="mr-1 text-[10px] text-faint">{m.venue === "H" ? "vs" : "@"}</span>
                {m.opponent}
              </td>
              <td className="py-1.5 pr-2 whitespace-nowrap">
                <span className={`mr-1.5 rounded px-1 text-[10px] font-bold ${resultChip[m.result]}`}>
                  {m.result}
                </span>
                {m.goals_for}–{m.goals_against}
              </td>
              <td className="py-1.5 pr-2">{m.total_goals}</td>
              <td className="py-1.5 pr-2 whitespace-nowrap">
                {m.total_corners ?? "—"}
                {m.total_corners !== null && (
                  <span className="ml-1 text-[10px] text-faint">({pair(m.corners_for, m.corners_against)})</span>
                )}
              </td>
              <td className="py-1.5 whitespace-nowrap">
                {pair(m.shots_on_target_for, m.shots_on_target_against)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TeamPanel({ form }: { form: TeamForm }) {
  if (form.club_key === null) {
    return (
      <div className="min-w-0 rounded-xl border border-dashed border-outline p-3">
        <p className="text-sm font-semibold text-ink">{form.team}</p>
        <p className="mt-1 text-xs text-faint">
          No stored history matches this name, so there is nothing to show rather than a guess.
        </p>
      </div>
    );
  }
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-sm font-semibold text-ink">{form.team}</p>
        <FormChips matches={form.matches} />
      </div>
      <AverageTiles averages={form.averages} />
      <div className="flex flex-wrap gap-1.5">
        {form.team_lines
          .filter((line) => line.sample > 0)
          .map((line) => (
            <span
              key={line.key}
              className="rounded-md border border-border bg-surface px-2 py-1 text-[11px] text-muted"
            >
              {line.label}{" "}
              <span className="font-semibold tabular-nums text-ink">
                {line.hits}/{line.sample}
              </span>
            </span>
          ))}
      </div>
      <MatchTable matches={form.matches} />
    </div>
  );
}

function TrendBoard({ insights, fixture }: { insights: MatchInsights; fixture: Fixture }) {
  const h2hSample = insights.head_to_head.matches.length;
  return (
    <div>
      <SectionLabel>Totals lines — how often they landed</SectionLabel>
      <div className="scroll-x rounded-xl border border-border bg-surface">
        <table className="w-full min-w-[30rem] text-left text-xs">
          <thead className="text-[10px] uppercase tracking-wider text-faint">
            <tr className="border-b border-hairline">
              <th className="px-3 py-2 font-semibold">Line</th>
              <th className="px-2 py-2 font-semibold" title={fixture.home_team}>
                {fixture.home_team}
              </th>
              <th className="px-2 py-2 font-semibold" title={fixture.away_team}>
                {fixture.away_team}
              </th>
              <th className="px-2 py-2 font-semibold">H2H</th>
              <th className="px-2 py-2 font-semibold" title="Distinct matches across all three samples">
                All
              </th>
              <th className="px-3 py-2 text-right font-semibold" title="Best price · de-margined implied probability">
                Book
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {insights.trends.map((row) => (
              <tr key={row.key}>
                <td className="px-3 py-2 font-medium whitespace-nowrap text-ink">{row.label}</td>
                <td className="px-2 py-2"><HitCell line={row.home} /></td>
                <td className="px-2 py-2"><HitCell line={row.away} /></td>
                <td className="px-2 py-2">{h2hSample ? <HitCell line={row.head_to_head} /> : <span className="text-faint">—</span>}</td>
                <td className="px-2 py-2 tabular-nums whitespace-nowrap text-muted-strong">
                  {row.pooled_sample ? formatPercent(row.pooled_hits / row.pooled_sample) : "—"}
                  <span className="ml-1 text-[10px] text-faint">n={row.pooled_sample}</span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums whitespace-nowrap">
                  {row.book_price !== null ? (
                    <>
                      <span className="font-semibold text-ink">{formatOdds(row.book_price)}</span>
                      {row.book_implied_prob !== null && (
                        <span className="ml-1.5 text-[10px] text-faint">{formatPercent(row.book_implied_prob)}</span>
                      )}
                    </>
                  ) : (
                    <span className="text-faint">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-faint">
        Sorted by strength of evidence (a 95% lower bound on the hit rate, so bigger samples rank
        higher), not by chance of winning. These are past frequencies from small samples — compare
        them with the book&apos;s implied probability rather than reading them as a prediction.
      </p>
    </div>
  );
}

function HeadToHeadPanel({ insights, fixture }: { insights: MatchInsights; fixture: Fixture }) {
  const h2h = insights.head_to_head;
  if (h2h.matches.length === 0) {
    return <p className="text-xs text-faint">No previous meetings in the stored history.</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      <StatGrid min="6.5rem">
        <Stat size="sm" label={fixture.home_team} value={h2h.home_wins} detail="wins" />
        <Stat size="sm" label="Draws" value={h2h.draws} />
        <Stat size="sm" label={fixture.away_team} value={h2h.away_wins} detail="wins" />
        <Stat
          size="sm"
          label="Avg goals"
          value={formatAverage(h2h.averages.total_goals)}
          detail={`corners ${formatAverage(h2h.averages.total_corners)}`}
        />
      </StatGrid>
      <p className="text-[11px] text-faint">
        Scores and stats are from {fixture.home_team}&apos;s side. Older meetings may reflect
        different squads and managers.
      </p>
      <MatchTable matches={h2h.matches} />
    </div>
  );
}

export function FixtureInsights({ fixture }: { fixture: Fixture }) {
  const [last, setLast] = useState<(typeof SAMPLE_SIZES)[number]>(5);
  const { data, isLoading, error } = useQuery({
    queryKey: ["fixture-insights", fixture.id, last],
    queryFn: () => fetchFixtureInsights(fixture.id, last),
    staleTime: 10 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-6 text-xs text-faint">
        <Spinner size="sm" /> Loading form and head-to-head…
      </div>
    );
  }
  if (error || !data) {
    return <p className="py-4 text-xs text-danger">Couldn&apos;t load insights for this fixture.</p>;
  }

  return (
    <div className="@container flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-faint">
          Last {last} matches per side, all competitions
          {data.data_through && <> · stored results through {formatDay(data.data_through)}</>}
        </p>
        <SegmentedControl
          label="Sample size"
          value={last}
          onChange={setLast}
          segments={SAMPLE_SIZES.map((n) => ({ value: n, label: `Last ${n}` }))}
        />
      </div>

      {data.stale && (
        <div className="flex items-start gap-2 rounded-xl border border-warn-line bg-warn-soft px-3 py-2 text-xs text-warn-strong">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>
            Stored results stop weeks before kickoff, so &ldquo;recent form&rdquo; here is out of date.
            Run <code className="font-mono">make sync-football-data-current</code> to refresh.
          </span>
        </div>
      )}

      <TrendBoard insights={data} fixture={fixture} />

      <div className="grid gap-5 @3xl:grid-cols-2">
        <TeamPanel form={data.home} />
        <TeamPanel form={data.away} />
      </div>

      <div>
        <SectionLabel>Head to head · last {data.head_to_head.matches.length}</SectionLabel>
        <HeadToHeadPanel insights={data} fixture={fixture} />
      </div>
    </div>
  );
}
