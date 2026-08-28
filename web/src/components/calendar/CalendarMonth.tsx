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
import { DayCell } from "./DayCell";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

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
  const currency = slips?.[0]?.currency ?? "USD";

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

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setMonth(addMonths(month, -1))}
            aria-label="Previous month"
            className="rounded-lg border border-[#E5E7EB] bg-white p-1.5 text-[#6B7280] transition-colors hover:bg-[#F3F4F6] hover:text-[#111827]"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            onClick={() => setMonth(addMonths(month, 1))}
            aria-label="Next month"
            className="rounded-lg border border-[#E5E7EB] bg-white p-1.5 text-[#6B7280] transition-colors hover:bg-[#F3F4F6] hover:text-[#111827]"
          >
            <ChevronRight size={16} />
          </button>
          <h2 className="ml-2 text-base font-semibold tracking-tight text-[#111827]">
            {monthLabel(month)}
          </h2>
          {month !== `${today.slice(0, 7)}-01` && (
            <button
              onClick={() => setMonth(`${today.slice(0, 7)}-01`)}
              className="ml-2 rounded-lg px-2.5 py-1 text-xs font-medium text-[#6C47FF] transition-colors hover:bg-[#EEE9FF]"
            >
              This month
            </button>
          )}
        </div>

        <div className="flex items-center gap-5 text-xs">
          <Stat label="Matches" value={String(totals.fixtures)} />
          <Stat label="Playable days" value={String(totals.playable)} />
          <Stat
            label={`P&L (${totals.settled} settled)`}
            value={totals.settled === 0 ? "—" : formatSignedCurrency(totals.pnl, currency)}
            tone={
              totals.settled === 0
                ? undefined
                : totals.pnl > 0
                  ? "text-[#059669]"
                  : totals.pnl < 0
                    ? "text-[#DC2626]"
                    : undefined
            }
          />
        </div>
      </div>

      {isError && (
        <div className="rounded-xl border border-[#FEE2E2] bg-[#FEE2E2]/50 px-4 py-3 text-sm text-[#DC2626]">
          {error instanceof Error ? error.message : "Failed to load the calendar."}
        </div>
      )}

      <div className="relative overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
        <div className="grid grid-cols-7 border-b border-[#E5E7EB] bg-[#FAFAFA]">
          {WEEKDAYS.map((d) => (
            <div
              key={d}
              className="px-2 py-2 text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]"
            >
              {d}
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
          <div className="absolute inset-0 flex items-center justify-center bg-white/70 backdrop-blur-[1px]">
            <SpinnerOverlay label="Loading month…" />
          </div>
        )}
      </div>

      <Legend />
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
        {label}
      </span>
      <span className={`text-sm font-semibold tabular-nums ${tone ?? "text-[#111827]"}`}>
        {value}
      </span>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-1 text-[11px] text-[#6B7280]">
      <span className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-[#059669]" />
        Strong slip available
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-[#D97706]" />
        Slip clears target, thinner edge
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-[#E5E7EB]" />
        No slip clears the target
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm bg-[#D1FAE5]" />
        Winning day
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm bg-[#FEE2E2]" />
        Losing day
      </span>
    </div>
  );
}
