"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { fetchCalendar, fetchSlips } from "@/lib/api";
import type { CalendarDay } from "@/lib/types";
import {
  addMonths,
  formatSignedCurrency,
  isSameMonth,
  monthGrid,
  monthLabel,
  todayISO,
} from "@/lib/utils";
import { SpinnerOverlay } from "@/components/ui/Spinner";
import { Stat, StatGrid, signTone } from "@/components/ui/Stat";
import { DayCell } from "./DayCell";

/** Short and single-letter forms; the narrow one needs the long one for a11y. */
const WEEKDAYS = [
  { short: "Mon", narrow: "M" },
  { short: "Tue", narrow: "T" },
  { short: "Wed", narrow: "W" },
  { short: "Thu", narrow: "T" },
  { short: "Fri", narrow: "F" },
  { short: "Sat", narrow: "S" },
  { short: "Sun", narrow: "S" },
];

function emptyDay(date: string): CalendarDay {
  return {
    date,
    fixture_count: 0,
    leagues: [],
    slip_count: 0,
    pending_count: 0,
    won_count: 0,
    lost_count: 0,
    staked: 0,
    profit_loss: 0,
    model: null,
  };
}

export function CalendarMonth() {
  const today = todayISO();
  const [month, setMonth] = useState(() => `${today.slice(0, 7)}-01`);

  const grid = useMemo(() => monthGrid(month), [month]);
  const from = grid[0];
  const to = grid[grid.length - 1];

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["calendar", from, to],
    queryFn: () => fetchCalendar(from, to),
  });

  const { data: slips } = useQuery({ queryKey: ["slips"], queryFn: fetchSlips });
  const currency = slips?.[0]?.currency ?? "ZAR";

  const byDate = useMemo(() => {
    const map = new Map<string, CalendarDay>();
    data?.days.forEach((d) => map.set(d.date, d));
    return map;
  }, [data]);

  // Month totals exclude the leading/trailing days borrowed from neighbouring
  // months, so the header reads as "this month" and not "these six weeks".
  const totals = useMemo(() => {
    const days = (data?.days ?? []).filter((d) => isSameMonth(d.date, month));
    return {
      fixtures: days.reduce((a, d) => a + d.fixture_count, 0),
      pnl: days.reduce((a, d) => a + d.profit_loss, 0),
      settled: days.reduce((a, d) => a + d.won_count + d.lost_count, 0),
      playable: days.filter((d) => d.model?.target_met).length,
    };
  }, [data, month]);

  const isCurrentMonth = month === `${today.slice(0, 7)}-01`;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-1">
        <button
          onClick={() => setMonth(addMonths(month, -1))}
          aria-label="Previous month"
          className="flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-surface text-muted transition-colors hover:bg-hairline hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:h-9 sm:w-9"
        >
          <ChevronLeft size={16} />
        </button>
        <button
          onClick={() => setMonth(addMonths(month, 1))}
          aria-label="Next month"
          className="flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-surface text-muted transition-colors hover:bg-hairline hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:h-9 sm:w-9"
        >
          <ChevronRight size={16} />
        </button>
        <h2 className="ml-2 min-w-0 flex-1 truncate text-base font-semibold tracking-tight text-ink">
          {monthLabel(month)}
        </h2>
        {!isCurrentMonth && (
          <button
            onClick={() => setMonth(`${today.slice(0, 7)}-01`)}
            className="flex min-h-[44px] shrink-0 items-center rounded-lg px-3 text-xs font-medium text-accent transition-colors hover:bg-accent-light focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[36px]"
          >
            This month
          </button>
        )}
      </div>

      <StatGrid min="8rem">
        <Stat label="Matches" value={totals.fixtures} />
        <Stat label="Playable days" value={totals.playable} />
        <Stat
          label={`P&L (${totals.settled} settled)`}
          value={
            totals.settled === 0 ? "—" : formatSignedCurrency(totals.pnl, currency)
          }
          tone={signTone(totals.pnl, totals.settled === 0)}
        />
      </StatGrid>

      {isError && (
        <div className="rounded-xl border border-danger-line bg-danger-faint px-4 py-3 text-sm text-danger">
          {error instanceof Error ? error.message : "Failed to load the calendar."}
        </div>
      )}

      <div className="relative overflow-hidden rounded-2xl border border-border bg-surface shadow-card">
        <div className="grid grid-cols-7 border-b border-border bg-canvas">
          {WEEKDAYS.map((d) => (
            <div
              key={d.short}
              className="px-1 py-2 text-center text-[10px] font-semibold uppercase tracking-wider text-faint sm:px-2 sm:text-left sm:tracking-widest"
            >
              <abbr title={d.short} className="no-underline sm:hidden">
                {d.narrow}
              </abbr>
              <span className="hidden sm:inline">{d.short}</span>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7 [&>a:nth-child(7n)]:border-r-0">
          {grid.map((iso) => (
            <DayCell
              key={iso}
              day={byDate.get(iso) ?? emptyDay(iso)}
              inMonth={isSameMonth(iso, month)}
              isToday={iso === today}
              currency={currency}
            />
          ))}
        </div>

        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface/70 backdrop-blur-[1px]">
            <SpinnerOverlay label="Loading month…" />
          </div>
        )}
      </div>

      <Legend />
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-1 text-[11px] text-muted sm:gap-x-5">
      <span className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-success" />
        Strong slip available
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-warn" />
        Slip clears target, thinner edge
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-border" />
        No slip clears the target
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm bg-success-soft" />
        Winning day
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm bg-danger-soft" />
        Losing day
      </span>
    </div>
  );
}
