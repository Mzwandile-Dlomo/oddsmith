"use client";

import { useState } from "react";
import type { Fixture } from "@/lib/types";
import { formatKickoffShort } from "@/lib/utils";
import { MarketPicker } from "./MarketPicker";
import { ChevronDown, Clock, Trophy } from "lucide-react";

interface FixtureCardProps {
  fixture: Fixture;
}

export function FixtureCard({ fixture }: FixtureCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="group bg-white transition-colors duration-150 hover:bg-[#FAFAFA]">
      <button
        className="w-full px-4 py-3.5 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#6C47FF]/30"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-col gap-1 min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="truncate text-sm font-semibold text-[#111827]">
                {fixture.home_team}
              </span>
              <span className="shrink-0 rounded bg-[#F3F4F6] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#9CA3AF]">
                vs
              </span>
              <span className="truncate text-sm font-semibold text-[#111827]">
                {fixture.away_team}
              </span>
            </div>
            <div className="flex items-center gap-3 text-[11px] text-[#9CA3AF]">
              {fixture.league && (
                <span className="flex items-center gap-1">
                  <Trophy size={10} className="shrink-0 text-[#6C47FF]/60" />
                  <span className="font-medium">{fixture.league}</span>
                </span>
              )}
              <span className="flex items-center gap-1">
                <Clock size={10} className="shrink-0" />
                {formatKickoffShort(fixture.kickoff_utc)}
              </span>
            </div>
          </div>
          <div
            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border transition-all duration-150 ${
              expanded
                ? "border-[#6C47FF]/30 bg-[#EEE9FF] text-[#6C47FF]"
                : "border-[#E5E7EB] bg-[#F9FAFB] text-[#9CA3AF] group-hover:border-[#D1D5DB] group-hover:text-[#6B7280]"
            }`}
          >
            <ChevronDown
              size={12}
              className={`transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
            />
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-[#F3F4F6] bg-[#FAFAFA]/70 px-4 pb-4 pt-3">
          <MarketPicker fixture={fixture} />
        </div>
      )}
    </div>
  );
}
