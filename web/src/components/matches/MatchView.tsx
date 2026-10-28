"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CalendarX, Clock, Sparkles, Trophy } from "lucide-react";
import { fetchFixtureInsights, fetchFixtures, fetchMatchRead } from "@/lib/api";
import type { Angle, Fixture, MatchInsights, MatchReadView, TeamForm, TeamMatch, TrendRow } from "@/lib/types";
import { dateFromISO, formatKickoff, formatPercent, todayISO } from "@/lib/utils";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton, SkeletonCard } from "@/components/ui/Spinner";
import { MarketPicker } from "@/components/fixtures/MarketPicker";
import { SlipDock } from "@/components/slip/SlipDock";
import { FormStrip, StrengthBadge, fmt, kickoffTimeKnown, matchDate } from "@/components/research/parts";

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-border bg-surface p-4 shadow-card sm:p-5">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Claude's read, or the computed headline alone when there is no written read. */
function ReadCard({ read, loading }: { read: MatchReadView | undefined; loading: boolean }) {
  if (loading) {
    return (
      <section className="flex flex-col gap-3 rounded-2xl border border-accent-line bg-accent-faint p-5">
        <p className="text-xs font-medium text-accent">Writing the match read…</p>
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-16 w-full" />
      </section>
    );
  }
  if (!read) return null;
  const top = read.angles.find((a) => a.key === read.angle_key) ?? read.angles[0];
  return (
    <section className="rounded-2xl border border-accent-line bg-accent-faint p-5">
      <p className="flex items-center gap-1.5 text-xs font-medium text-accent">
        <Sparkles size={13} /> Statistical read
      </p>
      {top ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold text-ink sm:text-xl">{top.label}</h2>
          <StrengthBadge angle={top} />
        </div>
      ) : (
        <h2 className="mt-2 text-lg font-semibold text-ink">No graded angle</h2>
      )}
      {read.summary && <p className="mt-3 text-sm leading-relaxed text-ink-soft">{read.summary}</p>}
      {read.match_read && (
        <p className="mt-3 border-t border-accent-line/60 pt-3 text-sm leading-relaxed text-ink-soft">
          <span className="font-medium text-ink">Match read: </span>
          {read.match_read}
        </p>
      )}
      {read.status !== "ok" && read.message && (
        <p className="mt-3 flex items-start gap-1.5 text-xs text-muted">
          <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warn" />
          {read.message}
        </p>
      )}
      {read.status === "ok" && read.model && (
        <p className="mt-3 text-[11px] text-faint">
          Written by {read.model} from the numbers below · a research angle, not a guaranteed result.
        </p>
      )}
    </section>
  );
}

function Tile({ label, home, away, names }: { label: string; home: string; away: string; names: [string, string] }) {
  return (
    <div className="min-w-0 rounded-xl border border-border bg-surface p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-tight text-ink">
        {home} <span className="text-faint">/</span> {away}
      </p>
      <p className="mt-0.5 truncate text-[11px] text-faint">
        {names[0]} / {names[1]}
      </p>
    </div>
  );
}

function lineCount(form: TeamForm, key: string): string {
  const line = form.total_lines.find((l) => l.key === key);
  return line && line.sample ? `${line.hits}/${line.sample}` : "—";
}

function StatTiles({ insights }: { insights: MatchInsights }) {
  const { home, away } = insights;
  const names: [string, string] = [home.team, away.team];
  const tiles: [string, string, string][] = [
    ["Goals scored / game", fmt(home.averages.goals_for), fmt(away.averages.goals_for)],
    ["Goals conceded / game", fmt(home.averages.goals_against), fmt(away.averages.goals_against)],
    ["Avg match goals", fmt(home.averages.total_goals), fmt(away.averages.total_goals)],
    ["Shots on target / game", fmt(home.averages.shots_on_target_for), fmt(away.averages.shots_on_target_for)],
    ["Shots on target faced / game", fmt(home.averages.shots_on_target_against), fmt(away.averages.shots_on_target_against)],
    ["Shots / game", fmt(home.averages.shots_for), fmt(away.averages.shots_for)],
    ["Match corners / game", fmt(home.averages.total_corners), fmt(away.averages.total_corners)],
    ["Both teams scored", lineCount(home, "btts_yes"), lineCount(away, "btts_yes")],
  ];
  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 lg:grid-cols-4">
      {tiles.map(([label, h, a]) => (
        <Tile key={label} label={label} home={h} away={a} names={names} />
      ))}
    </div>
  );
}

const cell = (v: number | null) => (v === null ? "—" : v);

function MatchTable({ matches, team, emptyText }: { matches: TeamMatch[]; team: string; emptyText: string }) {
  if (matches.length === 0) return <p className="text-sm text-muted">{emptyText}</p>;
  return (
    <div className="scroll-x -mx-4 sm:mx-0">
      <table className="w-full min-w-[40rem] text-sm">
        <thead>
          <tr className="text-left text-xs text-faint">
            <th className="px-4 py-2 font-medium sm:px-2">Date</th>
            <th className="px-2 py-2 font-medium">Opponent</th>
            <th className="px-2 py-2 font-medium">Score</th>
            <th className="px-2 py-2 text-right font-medium">Goals</th>
            <th className="px-2 py-2 text-right font-medium">Corners</th>
            <th className="px-2 py-2 text-right font-medium">{team} shots</th>
            <th className="px-2 py-2 text-right font-medium">{team} SOT</th>
            <th className="px-2 py-2 text-right font-medium">SOT faced</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {matches.map((m) => (
            <tr key={m.kickoff_utc} className="border-t border-hairline">
              <td className="whitespace-nowrap px-4 py-2 text-muted sm:px-2">
                {matchDate(m.kickoff_utc)}
              </td>
              <td className="max-w-[11rem] truncate px-2 py-2 text-ink">
                {m.opponent} <span className="text-faint">({m.venue})</span>
              </td>
              <td className="whitespace-nowrap px-2 py-2 text-ink">
                {m.goals_for}–{m.goals_against}{" "}
                <span
                  className={`ml-1 text-xs font-semibold ${
                    m.result === "W" ? "text-success" : m.result === "L" ? "text-danger" : "text-muted"
                  }`}
                >
                  {m.result}
                </span>
              </td>
              <td className="px-2 py-2 text-right text-ink">{m.total_goals}</td>
              <td className="px-2 py-2 text-right text-muted">{cell(m.total_corners)}</td>
              <td className="px-2 py-2 text-right text-muted">{cell(m.shots_for)}</td>
              <td className="px-2 py-2 text-right text-muted">{cell(m.shots_on_target_for)}</td>
              <td className="px-2 py-2 text-right text-muted">{cell(m.shots_on_target_against)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function count(line: { hits: number; sample: number }): string {
  return line.sample ? `${line.hits}/${line.sample}` : "—";
}

function TrendTable({ trends, angles, names }: { trends: TrendRow[]; angles: Angle[]; names: [string, string] }) {
  const graded = new Map(angles.map((a) => [a.key, a]));
  return (
    <div className="scroll-x -mx-4 sm:mx-0">
      <table className="w-full min-w-[42rem] text-sm">
        <thead>
          <tr className="text-left text-xs text-faint">
            <th className="px-4 py-2 font-medium sm:px-2">Line</th>
            <th className="max-w-[8rem] truncate px-2 py-2 text-right font-medium">{names[0]}</th>
            <th className="max-w-[8rem] truncate px-2 py-2 text-right font-medium">{names[1]}</th>
            <th className="px-2 py-2 font-medium">Both sides</th>
            <th className="px-2 py-2 text-right font-medium">Head-to-head</th>
            <th className="px-2 py-2 text-right font-medium">Best price</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {trends.map((row) => {
            const angle = graded.get(row.key);
            return (
              <tr key={row.key} className="border-t border-hairline">
                <td className="px-4 py-2 text-ink sm:px-2">{row.label}</td>
                <td className="px-2 py-2 text-right text-muted">{count(row.home)}</td>
                <td className="px-2 py-2 text-right text-muted">{count(row.away)}</td>
                <td className="px-2 py-2">
                  {angle ? <StrengthBadge angle={angle} /> : <span className="text-xs text-faint">Too few matches</span>}
                </td>
                <td className="px-2 py-2 text-right text-muted">{count(row.head_to_head)}</td>
                <td className="px-2 py-2 text-right">
                  {row.book_price === null ? (
                    <span className="text-faint">—</span>
                  ) : (
                    <span className="text-ink">
                      {row.book_price.toFixed(2)}
                      {row.book_implied_prob !== null && (
                        <span className="ml-1 text-xs text-faint">({formatPercent(row.book_implied_prob)})</span>
                      )}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function MatchView({ id, date }: { id: string; date: string | null }) {
  const day = date ?? todayISO();
  const d = dateFromISO(day);
  const from = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0).toISOString();
  const to = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59).toISOString();

  // Research reads stored data only; prices are refreshed by the scheduled sync.
  const fixturesQuery = useQuery({
    queryKey: ["fixtures", from, to, true],
    queryFn: () => fetchFixtures(from, to, true),
  });
  const insightsQuery = useQuery({
    queryKey: ["insights", id, 5],
    queryFn: () => fetchFixtureInsights(id, 5),
    retry: false,
  });
  const readQuery = useQuery({
    queryKey: ["match-read", id],
    queryFn: () => fetchMatchRead(id),
    retry: false,
    staleTime: 10 * 60_000,
  });
  const fixture: Fixture | undefined = fixturesQuery.data?.find((f) => f.id === id);
  const insights = insightsQuery.data;

  const back = (
    <Link
      href={day === todayISO() ? "/" : `/?date=${day}`}
      className="inline-flex min-h-[40px] items-center gap-1.5 self-start rounded-lg text-sm font-medium text-muted transition-colors hover:text-ink"
    >
      <ArrowLeft size={15} />
      Matches
    </Link>
  );

  if (insightsQuery.isError) {
    return (
      <div className="flex flex-col gap-4">
        {back}
        <EmptyState
          icon={<CalendarX size={22} />}
          title="Match not found"
          description="It may have been rescheduled or removed from the schedule. Open it again from the day's matches."
        />
      </div>
    );
  }

  const names: [string, string] = insights ? [insights.home.team, insights.away.team] : ["Home", "Away"];

  return (
    <SlipDock>
      <div className="flex flex-col gap-5">
        {back}

        <header className="rounded-2xl border border-border bg-surface px-5 py-6 shadow-panel sm:px-6">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
            {fixture?.league && (
              <span className="flex items-center gap-1.5">
                <Trophy size={12} className="text-accent" />
                {fixture.league}
              </span>
            )}
            {fixture && (
              <span className="flex items-center gap-1.5">
                <Clock size={12} />
                {kickoffTimeKnown(fixture)
                  ? formatKickoff(fixture.kickoff_utc)
                  : `${dateFromISO(day).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })} · time TBC`}
              </span>
            )}
          </div>
          {insights ? (
            <h1 className="mt-3 flex flex-col gap-1 text-xl font-semibold tracking-tight text-ink sm:flex-row sm:items-center sm:gap-3 sm:text-2xl">
              {insights.home.team}
              <span className="text-sm font-medium text-faint">vs</span>
              {insights.away.team}
            </h1>
          ) : (
            <Skeleton className="mt-3 h-8 w-2/3" />
          )}
          {insights && (
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted">
              Form (newest first)
              <FormStrip form={insights.home.matches.map((m) => m.result)} label={names[0]} />
              <span className="text-faint">/</span>
              <FormStrip form={insights.away.matches.map((m) => m.result)} label={names[1]} />
            </div>
          )}
        </header>

        <ReadCard read={readQuery.data} loading={readQuery.isLoading} />

        {insightsQuery.isLoading && <SkeletonCard />}
        {insights && (
          <>
            {insights.stale && (
              <p className="flex items-center gap-1.5 rounded-xl border border-warn-line bg-warn-soft/60 px-4 py-3 text-sm text-warn-strong">
                <AlertTriangle size={15} /> The results sync is behind, so a recent match may be missing below.
              </p>
            )}
            <StatTiles insights={insights} />

            {[insights.home, insights.away].map((form) => (
              <Section
                key={form.team}
                title={`${form.team} — previous ${form.matches.length || 5} matches`}
                note="Score from this side. A dash means the statistic wasn't recorded for that match."
              >
                <MatchTable
                  matches={form.matches}
                  team={form.team}
                  emptyText="No stored results under this club's name."
                />
              </Section>
            ))}

            <Section
              title="Head-to-head"
              note={
                insights.head_to_head.matches.length
                  ? `${names[0]} ${insights.head_to_head.home_wins}W · ${insights.head_to_head.draws}D · ${insights.head_to_head.away_wins}L in the last ${insights.head_to_head.matches.length} meetings. Score from ${names[0]}'s side.`
                  : undefined
              }
            >
              <MatchTable
                matches={insights.head_to_head.matches}
                team={names[0]}
                emptyText="No previous meetings stored."
              />
            </Section>

            <Section
              title="Over/under trend snapshot"
              note="Each side's last five, graded on both sides together. Best price is the highest bookmaker price collected, with its implied chance."
            >
              <TrendTable trends={insights.trends} angles={readQuery.data?.angles ?? []} names={names} />
            </Section>
          </>
        )}

        {fixture && (
          <Section
            title="Odds & bet slip"
            note="Prices from the last scheduled odds sync. Always confirm the price on your bookmaker before betting."
          >
            <MarketPicker fixture={fixture} />
          </Section>
        )}
      </div>
    </SlipDock>
  );
}
