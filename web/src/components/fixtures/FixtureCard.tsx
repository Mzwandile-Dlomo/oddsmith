"use client";

import Link from "next/link";
import { useState } from "react";
import type { Fixture } from "@/lib/types";
import { formatKickoffShort } from "@/lib/utils";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { FixtureInsights } from "./FixtureInsights";
import { MarketPicker } from "./MarketPicker";
import { ChevronDown, Clock, Trophy } from "lucide-react";

/** A match page is found by its kickoff day, so the URL carries both. */
export function matchHref(fixture: { id: string; kickoff_utc: string }): string {
  return `/matches/${encodeURIComponent(fixture.id)}?date=${fixture.kickoff_utc.slice(0, 10)}`;
}

interface FixtureCardProps {
  fixture: Fixture;
}

export function FixtureCard({ fixture }: FixtureCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [view, setView] = useState<"markets" | "insights">("markets");

  return (
    <div className="group bg-surface transition-colors duration-150 hover:bg-canvas">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <Link
          href={matchHref(fixture)}
          className="flex min-w-0 flex-1 flex-col gap-1 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
        >
          {/*
            Stacked on phones so both club names survive in full; a single
            "Home vs Away" line only leaves ~120px each at 375px, which cuts
            most real club names in half.
          */}
          <div className="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-2">
            <span className="truncate text-sm font-semibold text-ink">
              {fixture.home_team}
            </span>
            <span className="hidden shrink-0 rounded bg-hairline px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-faint sm:inline">
              vs
            </span>
            <span className="truncate text-sm font-semibold text-ink">
              {fixture.away_team}
            </span>
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-faint">
            {fixture.league && (
              <span className="flex min-w-0 items-center gap-1">
                <Trophy size={10} className="shrink-0 text-accent/60" />
                <span className="truncate font-medium">{fixture.league}</span>
              </span>
            )}
            <span className="flex shrink-0 items-center gap-1">
              <Clock size={10} className="shrink-0" />
              {formatKickoffShort(fixture.kickoff_utc)}
            </span>
          </div>
        </Link>
        <button
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          aria-label={expanded ? "Hide quick markets" : "Show quick markets"}
          title="Quick markets"
          className={`flex h-11 w-11 shrink-0 items-center sm:h-8 sm:w-8 justify-center rounded-full border transition-all duration-150 ${
            expanded
              ? "border-accent/30 bg-accent-light text-accent"
              : "border-border bg-subtle text-faint group-hover:border-outline group-hover:text-muted"
          }`}
        >
          <ChevronDown
            size={14}
            className={`transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
          />
        </button>
      </div>

      {expanded && (
        <div className="border-t border-hairline bg-canvas/70 px-4 pb-4 pt-3">
          <SegmentedControl
            label="Fixture view"
            value={view}
            onChange={setView}
            segments={[
              { value: "markets", label: "Markets" },
              { value: "insights", label: "Form & stats" },
            ]}
            className="mb-3"
          />
          {view === "markets" ? (
            <MarketPicker fixture={fixture} />
          ) : (
            <FixtureInsights fixture={fixture} />
          )}
        </div>
      )}
    </div>
  );
}
