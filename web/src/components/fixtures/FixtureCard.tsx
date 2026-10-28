"use client";

import { useState } from "react";
import type { Fixture } from "@/lib/types";
import { formatKickoffShort } from "@/lib/utils";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { FixtureInsights } from "./FixtureInsights";
import { MarketPicker } from "./MarketPicker";
import { ChevronDown, Clock, Trophy } from "lucide-react";

interface FixtureCardProps {
  fixture: Fixture;
}

export function FixtureCard({ fixture }: FixtureCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [view, setView] = useState<"markets" | "insights">("markets");

  return (
    <div className="group bg-surface transition-colors duration-150 hover:bg-canvas">
      <button
        className="w-full px-4 py-3 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
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
          </div>
          <span
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-all duration-150 ${
              expanded
                ? "border-accent/30 bg-accent-light text-accent"
                : "border-border bg-subtle text-faint group-hover:border-outline group-hover:text-muted"
            }`}
          >
            <ChevronDown
              size={14}
              className={`transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
            />
          </span>
        </div>
      </button>

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
