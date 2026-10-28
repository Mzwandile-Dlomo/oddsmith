"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchFixtures } from "@/lib/api";
import { addDays, toISODate, groupFixturesByDay } from "@/lib/utils";
import { SkeletonCard } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { FixtureCard } from "./FixtureCard";
import { CalendarDays } from "lucide-react";

type Timeframe = "today" | "3days" | "7days";

interface FixtureBrowserProps {
  timeframe: Timeframe;
  onTimeframeChange: (t: Timeframe) => void;
}

const TIMEFRAME_OPTIONS: { value: Timeframe; label: string; short: string }[] = [
  { value: "today", label: "Today", short: "Today" },
  { value: "3days", label: "Next 3 days", short: "3 days" },
  { value: "7days", label: "Next 7 days", short: "7 days" },
];

function getDateRange(tf: Timeframe): { from: string; to: string } {
  const now = new Date();
  const from = toISODate(now);
  if (tf === "today") return { from, to: from };
  if (tf === "3days") return { from, to: toISODate(addDays(now, 3)) };
  return { from, to: toISODate(addDays(now, 7)) };
}

export function FixtureBrowser({
  timeframe,
  onTimeframeChange,
}: FixtureBrowserProps) {
  const { from, to } = useMemo(() => getDateRange(timeframe), [timeframe]);

  const { data: fixtures, isLoading, isError, error } = useQuery({
    queryKey: ["fixtures", from, to],
    queryFn: () => fetchFixtures(from, to),
  });

  const grouped = useMemo(
    () => (fixtures ? groupFixturesByDay(fixtures) : []),
    [fixtures]
  );

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SegmentedControl
          label="Fixture window"
          value={timeframe}
          onChange={onTimeframeChange}
          segments={TIMEFRAME_OPTIONS.map((opt) => ({
            value: opt.value,
            label: (
              <>
                <span className="sm:hidden">{opt.short}</span>
                <span className="hidden sm:inline">{opt.label}</span>
              </>
            ),
          }))}
        />

        {fixtures && fixtures.length > 0 && (
          <span className="text-xs font-medium text-faint">
            {fixtures.length} {fixtures.length === 1 ? "match" : "matches"}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="flex flex-col gap-3">
          {[1, 2, 3].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-danger-line bg-danger-faint px-4 py-3 text-sm text-danger">
          {error instanceof Error ? error.message : "Failed to load fixtures. Is the backend running?"}
        </div>
      )}

      {!isLoading && !isError && fixtures && fixtures.length === 0 && (
        <EmptyState
          icon={<CalendarDays size={22} />}
          title="No fixtures in this window"
          description="The season may be on a break or no matches are scheduled for this timeframe. Try extending your window or check back later."
        />
      )}

      {/*
        The list flows with the page rather than scrolling inside a capped box.
        The old `calc(100vh - 220px)` container trapped the scroll gesture above
        the bet slip on mobile, and `100vh` is wrong under iOS Safari's URL bar.
        Day headers stick to the app chrome instead of to an inner container.
      */}
      {!isLoading && !isError && grouped.length > 0 && (
        <div className="overflow-clip rounded-2xl border border-border bg-surface shadow-card">
          {grouped.map((group) => (
            <div key={group.isoDate}>
              <div className="sticky top-14 z-10 flex items-center gap-3 border-b border-hairline bg-canvas/95 px-4 py-2.5 backdrop-blur-sm">
                <CalendarDays size={13} className="shrink-0 text-accent" />
                <span className="truncate text-xs font-semibold uppercase tracking-widest text-muted">
                  {group.label}
                </span>
                <span className="ml-auto shrink-0 text-xs text-faint">
                  {group.items.length}
                </span>
              </div>
              <div className="flex flex-col divide-y divide-hairline">
                {group.items.map((fixture) => (
                  <FixtureCard key={fixture.id} fixture={fixture} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export type { Timeframe };
