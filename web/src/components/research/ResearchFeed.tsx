"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDeferredValue, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarX, ChevronLeft, ChevronRight, Search, Tag } from "lucide-react";
import { fetchResearchDay } from "@/lib/api";
import type { ResearchCard } from "@/lib/types";
import { addDays, dateFromISO, parseKickoff, toLocalISODate, todayISO } from "@/lib/utils";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/Spinner";
import { FormStrip, StrengthBadge, fmt, localTime } from "./parts";

/** A match page is found by its local day, so the URL carries both. */
export function researchHref(card: { fixture_id: string }, day: string): string {
  return `/matches/${encodeURIComponent(card.fixture_id)}?date=${day}`;
}

// A match runs ~2h with stoppages; past that, a missing score means the results sync hasn't caught up.
const MATCH_LENGTH_MS = 2 * 60 * 60_000;

function Card({ card, day }: { card: ResearchCard; day: string }) {
  const [top, second] = card.angles;
  const finished = card.home_score !== null && card.away_score !== null;
  const awaitingResult =
    !finished && card.time_confirmed && Date.now() - parseKickoff(card.kickoff_utc).getTime() > MATCH_LENGTH_MS;
  return (
    <Link
      href={researchHref(card, day)}
      className="group flex min-w-0 flex-col gap-3 rounded-2xl border border-border bg-surface p-4 shadow-card transition-colors hover:border-accent/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:p-5"
    >
      <div className="flex items-center justify-between gap-3 text-xs text-muted">
        <span className="truncate">
          {card.league ?? "Unknown competition"} · {card.time_confirmed ? localTime(card.kickoff_utc) : "Time TBC"}
        </span>
        {card.priced && (
          <span className="flex shrink-0 items-center gap-1 rounded-full border border-info-line bg-info-faint px-2 py-0.5 text-[10px] font-semibold text-info">
            <Tag size={10} /> Odds
          </span>
        )}
      </div>

      <div className="flex items-start justify-between gap-3">
        <h2 className="text-base font-semibold leading-snug text-ink group-hover:text-accent">
          {card.home_team} <span className="text-sm font-normal text-faint">vs</span> {card.away_team}
        </h2>
        {finished && (
          <span className="flex shrink-0 items-baseline gap-1.5 rounded-lg border border-border bg-hairline px-2 py-0.5">
            <span className="text-[10px] font-semibold uppercase text-faint">FT</span>
            <span className="text-sm font-semibold tabular-nums text-ink">
              {card.home_score}–{card.away_score}
            </span>
          </span>
        )}
        {awaitingResult && <span className="shrink-0 pt-0.5 text-[11px] text-faint">Result not synced yet</span>}
      </div>

      {top ? (
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-ink">{top.label}</span>
            <StrengthBadge angle={top} />
          </div>
          {second && (
            <p className="text-xs text-muted">
              Also: {second.label} <span className="tabular-nums">({second.hits}/{second.sample})</span>
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted">
          {card.has_history ? "Not enough recent matches to grade a line." : "No stored history for one of these clubs."}
        </p>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 border-t border-hairline pt-3 text-xs">
        <div className="min-w-0">
          <dt className="text-faint">Goals scored / game</dt>
          <dd className="tabular-nums text-ink">
            {fmt(card.home_goals_for)} – {fmt(card.away_goals_for)}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-faint">Avg match goals</dt>
          <dd className="tabular-nums text-ink">
            {fmt(card.home_avg_total_goals)} – {fmt(card.away_avg_total_goals)}
          </dd>
        </div>
        <div className="col-span-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          <dt className="text-faint">Form</dt>
          <dd className="flex flex-wrap items-center gap-2">
            <FormStrip form={card.home_form} label={card.home_team} />
            <span className="text-faint">/</span>
            <FormStrip form={card.away_form} label={card.away_team} />
          </dd>
        </div>
      </dl>
      {card.stale && (
        <p className="text-[11px] text-warn">Results sync is behind; recent form may be missing a match.</p>
      )}
    </Link>
  );
}

export function ResearchFeed({ initialDay }: { initialDay: string | null }) {
  const router = useRouter();
  const day = initialDay ?? todayISO();
  const [league, setLeague] = useState("");
  const [query, setQuery] = useState("");
  const needle = useDeferredValue(query.trim().toLowerCase());

  // The local day as two instants, so a 01:00 kickoff lands on the day it is played here.
  const d = dateFromISO(day);
  const from = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0).toISOString();
  const to = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59).toISOString();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["research-day", from, to],
    queryFn: () => fetchResearchDay(from, to),
    staleTime: 5 * 60_000,
  });

  const cards = useMemo(
    () =>
      (data?.cards ?? []).filter(
        (c) =>
          (!league || c.league === league) &&
          (!needle || `${c.home_team} ${c.away_team}`.toLowerCase().includes(needle))
      ),
    [data, league, needle]
  );

  const go = (next: string) => router.push(next === todayISO() ? "/" : `/?date=${next}`);
  const shift = (days: number) => go(toLocalISODate(addDays(d, days)));
  const label = d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center rounded-xl border border-border bg-surface p-1 shadow-card">
          <button
            onClick={() => shift(-1)}
            aria-label="Previous day"
            className="flex h-10 w-10 items-center justify-center rounded-lg text-muted hover:bg-hairline hover:text-ink sm:h-8 sm:w-8"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="min-w-[10rem] px-2 text-center text-sm font-medium text-ink">
            {day === todayISO() ? `Today · ${label.split(" ").slice(1).join(" ")}` : label}
          </span>
          <button
            onClick={() => shift(1)}
            aria-label="Next day"
            className="flex h-10 w-10 items-center justify-center rounded-lg text-muted hover:bg-hairline hover:text-ink sm:h-8 sm:w-8"
          >
            <ChevronRight size={16} />
          </button>
        </div>
        <label className="sr-only" htmlFor="feed-date">Pick a date</label>
        <input
          id="feed-date"
          type="date"
          value={day}
          onChange={(e) => e.target.value && go(e.target.value)}
          className="h-12 rounded-xl border border-border bg-surface px-3 text-sm text-ink [color-scheme:dark] sm:h-10"
        />
        <label className="sr-only" htmlFor="feed-league">Competition</label>
        <select
          id="feed-league"
          value={league}
          onChange={(e) => setLeague(e.target.value)}
          className="h-12 rounded-xl border border-border bg-surface px-3 text-sm text-ink sm:h-10"
        >
          <option value="">All competitions</option>
          {(data?.leagues ?? []).map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <div className="relative min-w-[12rem] flex-1 sm:max-w-xs">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <label className="sr-only" htmlFor="feed-search">Search teams</label>
          <input
            id="feed-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search this day's teams…"
            className="h-12 w-full rounded-xl border border-border bg-surface pl-9 pr-3 text-base text-ink placeholder:text-faint focus:border-accent/60 focus:outline-none sm:h-10 sm:text-sm"
          />
        </div>
      </div>

      {isLoading && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted">Pulling form and trends for every match…</p>
          <div className="grid gap-4 xl:grid-cols-2">
            {[1, 2, 3, 4].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        </div>
      )}
      {isError && (
        <div className="rounded-xl border border-danger-line bg-danger-faint px-4 py-3 text-sm text-danger">
          {error instanceof Error ? error.message : "Could not load matches. Is the backend running?"}
        </div>
      )}
      {data && cards.length === 0 && (
        <EmptyState
          icon={<CalendarX size={22} />}
          title={data.cards.length ? "No matches fit those filters" : "No matches stored for this day"}
          description={
            data.cards.length
              ? "Clear the competition or search to see every match."
              : "Fixtures appear once the schedule sync has run for these competitions."
          }
        />
      )}
      {cards.length > 0 && (
        <>
          <p className="text-xs text-faint">
            {cards.length} {cards.length === 1 ? "match" : "matches"} · angles graded from each side&apos;s last five
          </p>
          <div className="grid gap-4 xl:grid-cols-2">
            {cards.map((card) => (
              <Card key={card.fixture_id} card={card} day={day} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
