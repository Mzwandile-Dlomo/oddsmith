"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateSlip } from "@/lib/api";
import type { LegResult, LegUpdate, SlipUpdate, SlipView } from "@/lib/types";
import {
  formatCurrency,
  formatKickoff,
  formatOdds,
  legLabel,
  resultBadgeClass,
} from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ChevronDown } from "lucide-react";

const LEG_RESULT_OPTIONS: { value: LegResult; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
  { value: "void", label: "Void" },
];

interface SlipCardProps {
  slip: SlipView;
}

export function SlipCard({ slip }: SlipCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [legResults, setLegResults] = useState<Record<number, LegResult>>(
    () =>
      Object.fromEntries(slip.legs.map((l) => [l.id, l.result]))
  );
  const [settleError, setSettleError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (body: SlipUpdate) => updateSlip(slip.id, body),
    onSuccess: () => {
      setSettleError(null);
      queryClient.invalidateQueries({ queryKey: ["slips"] });
    },
    onError: (err) => {
      setSettleError(err instanceof Error ? err.message : "Settle failed");
    },
  });

  const handleSettle = () => {
    const legs: LegUpdate[] = slip.legs.map((l) => ({
      leg_id: l.id,
      result: legResults[l.id] ?? l.result,
    }));
    const body: SlipUpdate = { legs };
    mutation.mutate(body);
  };

  const isPending = slip.result === "pending";

  return (
    <Card className="overflow-hidden">
      <button
        className="w-full px-4 py-4 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#6C47FF]/30"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-1.5 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-semibold text-[#111827]">
                {slip.name ?? `Slip #${slip.id}`}
              </span>
              <Badge className={resultBadgeClass(slip.result)}>
                {slip.result}
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#6B7280]">
              <span>
                <span className="font-medium text-[#111827]">
                  {slip.legs.length}
                </span>{" "}
                {slip.legs.length === 1 ? "leg" : "legs"}
              </span>
              <span>
                Odds:{" "}
                <span className="font-semibold text-[#6C47FF]">
                  {formatOdds(slip.combined_odds)}
                </span>
              </span>
              <span>
                Stake:{" "}
                <span className="font-medium text-[#111827]">
                  {formatCurrency(slip.stake, slip.currency)}
                </span>
              </span>
              {slip.result !== "pending" && (
                <span
                  className={
                    slip.profit_loss >= 0
                      ? "font-semibold text-[#059669]"
                      : "font-semibold text-[#DC2626]"
                  }
                >
                  {slip.profit_loss >= 0 ? "+" : ""}
                  {formatCurrency(slip.profit_loss, slip.currency)}
                </span>
              )}
            </div>
          </div>
          <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border transition-all duration-150 mt-0.5 ${
            expanded
              ? "border-[#6C47FF]/30 bg-[#EEE9FF] text-[#6C47FF]"
              : "border-[#E5E7EB] bg-[#F9FAFB] text-[#9CA3AF]"
          }`}>
            <ChevronDown
              size={12}
              className={`transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
            />
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-[#F3F4F6] px-4 pb-4 pt-3">
          <div className="flex flex-col gap-2 mb-4">
            {slip.legs.map((leg) => {
              const label = legLabel(
                leg.market_type,
                leg.selection,
                leg.point,
                leg.home_team,
                leg.away_team
              );
              const currentResult = legResults[leg.id] ?? leg.result;
              return (
                <div
                  key={leg.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-[#F3F4F6] bg-[#FAFAFA] px-3 py-2.5"
                >
                  <div className="min-w-0 flex flex-col gap-0.5">
                    <span className="truncate text-[11px] text-[#9CA3AF]">
                      {leg.home_team} vs {leg.away_team}
                    </span>
                    <span className="text-sm font-medium leading-tight text-[#111827]">
                      {label}
                    </span>
                    <span className="text-[11px] text-[#9CA3AF]">
                      {formatKickoff(leg.kickoff_utc)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-sm font-bold tabular-nums text-[#6B7280]">
                      {formatOdds(leg.price)}
                    </span>
                    {isPending ? (
                      <select
                        value={currentResult}
                        onChange={(e) =>
                          setLegResults((prev) => ({
                            ...prev,
                            [leg.id]: e.target.value as LegResult,
                          }))
                        }
                        className="rounded-lg border border-[#E5E7EB] bg-white px-2 py-1 text-xs text-[#111827] transition-colors duration-150 focus:border-[#6C47FF] focus:outline-none focus:ring-2 focus:ring-[#6C47FF]/20"
                      >
                        {LEG_RESULT_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Badge className={resultBadgeClass(leg.result)}>
                        {leg.result}
                      </Badge>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 rounded-xl border border-[#F3F4F6] bg-[#FAFAFA] px-3.5 py-3 text-xs">
            <div className="flex items-center gap-1 text-[#6B7280]">
              Combined odds:
              <span className="ml-1 font-bold tabular-nums text-[#6C47FF]">
                {formatOdds(slip.combined_odds)}
              </span>
            </div>
            <div className="flex items-center gap-1 text-[#6B7280]">
              Potential return:
              <span className="ml-1 font-semibold tabular-nums text-[#111827]">
                {formatCurrency(slip.potential_return, slip.currency)}
              </span>
            </div>
            {slip.result !== "pending" && (
              <>
                <div className="flex items-center gap-1 text-[#6B7280]">
                  Payout:
                  <span className="ml-1 font-semibold tabular-nums text-[#111827]">
                    {formatCurrency(slip.payout, slip.currency)}
                  </span>
                </div>
                <div className="flex items-center gap-1 text-[#6B7280]">
                  P&L:
                  <span
                    className={`ml-1 font-bold tabular-nums ${
                      slip.profit_loss >= 0
                        ? "text-[#059669]"
                        : "text-[#DC2626]"
                    }`}
                  >
                    {slip.profit_loss >= 0 ? "+" : ""}
                    {formatCurrency(slip.profit_loss, slip.currency)}
                  </span>
                </div>
              </>
            )}
          </div>

          {settleError && (
            <p className="mb-2 rounded-lg bg-[#FEE2E2]/60 px-3 py-2 text-xs text-[#DC2626]">
              {settleError}
            </p>
          )}

          {isPending && (
            <Button
              onClick={handleSettle}
              disabled={mutation.isPending}
              variant="secondary"
              size="sm"
            >
              {mutation.isPending ? (
                <>
                  <Spinner size="sm" />
                  Settling…
                </>
              ) : (
                "Settle"
              )}
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}
