"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchFixtures } from "@/lib/api";
import { addDays, toISODate, groupFixturesByDay } from "@/lib/utils";
import { SkeletonCard } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { FixtureCard } from "./FixtureCard";
import { CalendarDays } from "lucide-react";

type Timeframe = "today" | "3days" | "7days";

interface FixtureBrowserProps {
  timeframe: Timeframe;
  onTimeframeChange: (t: Timeframe) => void;
}

const TIMEFRAME_OPTIONS: { value: Timeframe; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "3days", label: "Next 3 days" },
  { value: "7days", label: "Next 7 days" },
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
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1 rounded-xl border border-[#E5E7EB] bg-white p-1 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          {TIMEFRAME_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onTimeframeChange(opt.value)}
              className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-all duration-150 ${
                timeframe === opt.value
                  ? "bg-[#6C47FF] text-white shadow-sm"
                  : "text-[#6B7280] hover:bg-[#F3F4F6] hover:text-[#111827]"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {fixtures && fixtures.length > 0 && (
          <span className="text-xs font-medium text-[#9CA3AF]">
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
        <div className="rounded-xl border border-[#FEE2E2] bg-[#FEE2E2]/50 px-4 py-3 text-sm text-[#DC2626]">
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

      {!isLoading && !isError && grouped.length > 0 && (
        <div className="relative overflow-y-auto rounded-2xl border border-[#E5E7EB] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06)]" style={{ maxHeight: "calc(100vh - 220px)" }}>
          {grouped.map((group) => (
            <div key={group.isoDate}>
              <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-[#F3F4F6] bg-[#FAFAFA]/95 px-4 py-2.5 backdrop-blur-sm">
                <CalendarDays size={13} className="text-[#6C47FF]" />
                <span className="text-xs font-semibold uppercase tracking-widest text-[#6B7280]">
                  {group.label}
                </span>
                <span className="ml-auto text-xs text-[#9CA3AF]">
                  {group.items.length}
                </span>
              </div>
              <div className="flex flex-col divide-y divide-[#F3F4F6]">
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
