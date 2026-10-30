"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateSlip } from "@/lib/api";
import type { LegResult, LegUpdate, SlipUpdate, SlipView } from "@/lib/types";
import {
  formatCurrency,
  formatKickoff,
  formatOdds,
  hasFinished,
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
      // The month and day views derive their win/loss markers from `/calendar`,
      // not the locally cached slip. Refresh it as soon as an outcome is
      // recorded so a settled paper ticket immediately marks its match day.
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      // A settled generated paper ticket also contributes to the evidence shown
      // in Model Lab's paper-performance panel.
      queryClient.invalidateQueries({ queryKey: ["paper-performance"] });
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

  /*
    A leg is settleable whenever it is still pending — not only while the whole
    slip is. An acca goes LOST the moment one leg loses, and gating on the slip
    left the other legs stranded on "pending" with no control to correct them,
    even months after they kicked off.
  */
  const hasPendingLeg = slip.legs.some((l) => l.result === "pending");
  const decidedWithPendingLegs = slip.result !== "pending" && hasPendingLeg;

  return (
    <Card className="overflow-hidden">
      <button
        className="w-full px-4 py-4 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-1.5 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-semibold text-ink">
                {slip.name ?? `Slip #${slip.id}`}
              </span>
              <Badge className={resultBadgeClass(slip.result)}>
                {slip.result}
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
              <span>
                <span className="font-medium text-ink">
                  {slip.legs.length}
                </span>{" "}
                {slip.legs.length === 1 ? "leg" : "legs"}
              </span>
              <span>
                Odds:{" "}
                <span className="font-semibold text-accent">
                  {formatOdds(slip.combined_odds)}
                </span>
              </span>
              <span>
                Stake:{" "}
                <span className="font-medium text-ink">
                  {formatCurrency(slip.stake, slip.currency)}
                </span>
              </span>
              {slip.result !== "pending" && (
                <span
                  className={
                    slip.profit_loss >= 0
                      ? "font-semibold text-success"
                      : "font-semibold text-danger"
                  }
                >
                  {slip.profit_loss >= 0 ? "+" : ""}
                  {formatCurrency(slip.profit_loss, slip.currency)}
                </span>
              )}
            </div>
          </div>
          <span className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-all duration-150 ${
            expanded
              ? "border-accent/30 bg-accent-light text-accent"
              : "border-border bg-subtle text-faint"
          }`}>
            <ChevronDown
              size={14}
              className={`transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
            />
          </span>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-hairline px-4 pb-4 pt-3">
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
                  className="flex flex-col gap-2 rounded-xl border border-hairline bg-canvas px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-3"
                >
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="truncate text-[11px] text-faint">
                      {leg.home_team} vs {leg.away_team}
                    </span>
                    <span className="text-sm font-medium leading-tight text-ink">
                      {label}
                    </span>
                    <span className="text-[11px] text-faint">
                      {formatKickoff(leg.kickoff_utc)}
                      {leg.home_score !== null && leg.away_score !== null && (
                        <>
                          {" · "}
                          <span className="font-semibold tabular-nums text-ink">
                            FT {leg.home_score}–{leg.away_score}
                          </span>
                        </>
                      )}
                      {/* A corners leg is decided by corners, so show the number it was graded on. */}
                      {leg.market_type === "corner_totals" &&
                        leg.home_corners !== null &&
                        leg.away_corners !== null && (
                          <span className="tabular-nums">
                            {" · "}Corners {leg.home_corners}–{leg.away_corners}
                          </span>
                        )}
                    </span>
                    {/*
                      "Pending" on a match that finished days ago reads as if
                      the app thinks it hasn't kicked off. It has — no result
                      feed covers it, which is a different thing and the user's
                      cue to settle it by hand.
                    */}
                    {leg.result === "pending" && hasFinished(leg.kickoff_utc) && (
                      <span
                        title="This match has finished, but no result has come through for it. Set the outcome yourself if you know it."
                        className="mt-1 inline-flex w-fit items-center rounded-full border border-warn/20 bg-warn-soft px-2 py-0.5 text-[10px] font-medium text-warn"
                      >
                        Awaiting result
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-sm font-bold tabular-nums text-muted">
                      {formatOdds(leg.price)}
                    </span>
                    {leg.result === "pending" ? (
                      <>
                        {/* Settling is this page's whole job, so the control
                            takes a full-width 44px target on a phone. */}
                        <label className="sr-only" htmlFor={`leg-result-${leg.id}`}>
                          Result for {label}
                        </label>
                        <select
                          id={`leg-result-${leg.id}`}
                          value={currentResult}
                          onChange={(e) =>
                            setLegResults((prev) => ({
                              ...prev,
                              [leg.id]: e.target.value as LegResult,
                            }))
                          }
                          className="min-h-[44px] w-full rounded-lg border border-border bg-surface px-2 text-sm text-ink transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 sm:min-h-[32px] sm:w-auto sm:text-xs"
                        >
                          {LEG_RESULT_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </>
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

          <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 rounded-xl border border-hairline bg-canvas px-3.5 py-3 text-xs">
            <div className="flex items-center gap-1 text-muted">
              Combined odds:
              <span className="ml-1 font-bold tabular-nums text-accent">
                {formatOdds(slip.combined_odds)}
              </span>
            </div>
            <div className="flex items-center gap-1 text-muted">
              Potential return:
              <span className="ml-1 font-semibold tabular-nums text-ink">
                {formatCurrency(slip.potential_return, slip.currency)}
              </span>
            </div>
            {slip.result !== "pending" && (
              <>
                <div className="flex items-center gap-1 text-muted">
                  Payout:
                  <span className="ml-1 font-semibold tabular-nums text-ink">
                    {formatCurrency(slip.payout, slip.currency)}
                  </span>
                </div>
                <div className="flex items-center gap-1 text-muted">
                  P&L:
                  <span
                    className={`ml-1 font-bold tabular-nums ${
                      slip.profit_loss >= 0
                        ? "text-success"
                        : "text-danger"
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
            <p className="mb-2 rounded-lg bg-danger-soft/60 px-3 py-2 text-xs text-danger">
              {settleError}
            </p>
          )}

          {decidedWithPendingLegs && (
            <p className="mb-2 text-[11px] leading-relaxed text-faint">
              This slip is already settled as {slip.result} — one lost leg
              decides an acca — so recording the rest will not change the P&amp;L.
              It only completes the record.
            </p>
          )}

          {hasPendingLeg && (
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
