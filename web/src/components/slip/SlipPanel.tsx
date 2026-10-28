"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createSlip } from "@/lib/api";
import type { SlipCreate } from "@/lib/types";
import { useSlipStore } from "@/store/slip-store";
import { formatCurrency, formatOdds, legLabel } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { X, Trash2, Receipt } from "lucide-react";

interface SlipPanelProps {
  onSlipSaved: () => void;
  /** The mobile sheet renders its own title bar, so the panel skips one. */
  hideHeader?: boolean;
}

/** 16px minimum on phones — anything smaller makes iOS Safari zoom on focus. */
const inputClasses =
  "w-full min-h-[44px] rounded-lg border border-border bg-surface px-3 text-base text-ink placeholder:text-faint transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 sm:min-h-[38px] sm:text-sm";

export function SlipPanel({ onSlipSaved, hideHeader = false }: SlipPanelProps) {
  const { legs, removeLeg, clearLegs, computedOdds } = useSlipStore();
  const [slipName, setSlipName] = useState("");
  const [stake, setStake] = useState<string>("10");
  const [saveError, setSaveError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const stakeNum = parseFloat(stake) || 0;
  const potentialReturn = computedOdds * stakeNum;
  const potentialProfit = potentialReturn - stakeNum;

  const mutation = useMutation({
    mutationFn: (body: SlipCreate) => createSlip(body),
    onSuccess: () => {
      clearLegs();
      setSlipName("");
      setStake("10");
      setSaveError(null);
      queryClient.invalidateQueries({ queryKey: ["slips"] });
      onSlipSaved();
    },
    onError: (err) => {
      setSaveError(err instanceof Error ? err.message : "Failed to save slip");
    },
  });

  const handleSave = () => {
    if (legs.length === 0) return;
    setSaveError(null);
    const body: SlipCreate = {
      name: slipName.trim() || null,
      stake: stakeNum > 0 ? stakeNum : undefined,
      currency: "ZAR",
      legs: legs.map((l) => ({
        fixture_id: l.fixture_id,
        home_team: l.home_team,
        away_team: l.away_team,
        kickoff_utc: l.kickoff_utc,
        league: l.league,
        provider: l.provider,
        market_type: l.market_type,
        selection: l.selection,
        point: l.point,
        price: l.price,
      })),
    };
    mutation.mutate(body);
  };

  return (
    <div className="flex flex-col">
      {!hideHeader && (
        <div className="flex items-center justify-between gap-2 border-b border-hairline px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <Receipt size={15} className="shrink-0 text-accent" />
            <span className="text-sm font-semibold text-ink">Bet Slip</span>
            {legs.length > 0 && (
              <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-accent px-1.5 text-[10px] font-bold text-canvas">
                {legs.length}
              </span>
            )}
          </div>
          {legs.length > 0 && (
            <button
              onClick={clearLegs}
              className="-mr-1 flex min-h-[40px] shrink-0 items-center gap-1 rounded-lg px-2 text-xs text-faint transition-colors duration-150 hover:bg-danger-soft/60 hover:text-danger sm:min-h-[32px]"
            >
              <Trash2 size={12} />
              Clear
            </button>
          )}
        </div>
      )}

      {legs.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2.5 px-4 py-12 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-hairline">
            <Receipt size={18} className="text-faint" />
          </div>
          <p className="text-sm font-medium text-muted">Slip is empty</p>
          <p className="text-xs text-faint">
            Pick an outcome from any match to start building
          </p>
        </div>
      ) : (
        <div className="flex flex-col">
          {hideHeader && (
            <div className="flex justify-end px-4 pt-3">
              <button
                onClick={clearLegs}
                className="flex min-h-[40px] items-center gap-1 rounded-lg px-2 text-xs text-faint transition-colors hover:bg-danger-soft/60 hover:text-danger"
              >
                <Trash2 size={12} />
                Clear all
              </button>
            </div>
          )}

          <div className="flex flex-col divide-y divide-hairline">
            {legs.map((leg) => {
              const label = legLabel(
                leg.market_type,
                leg.selection,
                leg.point,
                leg.home_team,
                leg.away_team
              );
              return (
                <div
                  key={leg.key}
                  className="flex items-start justify-between gap-2 px-4 py-3"
                >
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="truncate text-[11px] text-faint">
                      {leg.home_team} vs {leg.away_team}
                    </span>
                    <span className="text-sm font-medium leading-tight text-ink">
                      {label}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <span className="text-sm font-bold tabular-nums text-accent">
                      {formatOdds(leg.price)}
                    </span>
                    <button
                      onClick={() => removeLeg(leg.key)}
                      className="-mr-1 flex h-11 w-11 items-center justify-center rounded-lg text-outline transition-colors duration-150 hover:bg-danger-soft/50 hover:text-danger sm:h-8 sm:w-8"
                      aria-label={`Remove ${label}`}
                    >
                      <X size={15} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex flex-col gap-3.5 border-t border-hairline bg-canvas p-4">
            <div className="flex items-center justify-between rounded-xl bg-accent-light px-3.5 py-2.5">
              <span className="text-xs font-medium text-accent/70">
                Combined odds
              </span>
              <span className="text-base font-bold tabular-nums text-accent">
                {formatOdds(computedOdds)}
              </span>
            </div>

            {/* Side by side once there is room; stacked on the narrowest phones. */}
            <div className="grid gap-3.5 min-[420px]:grid-cols-2 lg:grid-cols-1">
              <div>
                <label
                  htmlFor="stake"
                  className="mb-1.5 block text-xs font-medium text-muted"
                >
                  Stake (R)
                </label>
                <input
                  id="stake"
                  type="number"
                  inputMode="decimal"
                  min={0.01}
                  step={0.01}
                  value={stake}
                  onChange={(e) => setStake(e.target.value)}
                  className={`${inputClasses} tabular-nums`}
                  placeholder="10.00"
                />
              </div>

              <div>
                <label
                  htmlFor="slip-name"
                  className="mb-1.5 block text-xs font-medium text-muted"
                >
                  Slip name <span className="text-faint">(optional)</span>
                </label>
                <input
                  id="slip-name"
                  type="text"
                  value={slipName}
                  onChange={(e) => setSlipName(e.target.value)}
                  className={inputClasses}
                  placeholder="My weekend slip"
                />
              </div>
            </div>

            {stakeNum > 0 && (
              <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-surface p-3 text-xs">
                <div className="flex items-center justify-between gap-3 text-muted">
                  <span>Potential return</span>
                  <span className="font-semibold tabular-nums text-ink">
                    {formatCurrency(potentialReturn)}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3 text-muted">
                  <span>Potential profit</span>
                  <span
                    className={`font-semibold tabular-nums ${
                      potentialProfit >= 0 ? "text-success" : "text-danger"
                    }`}
                  >
                    {formatCurrency(potentialProfit)}
                  </span>
                </div>
              </div>
            )}

            {saveError && (
              <p className="rounded-lg bg-danger-soft/60 px-3 py-2 text-xs text-danger">
                {saveError}
              </p>
            )}

            <Button
              onClick={handleSave}
              disabled={legs.length === 0 || mutation.isPending}
              className="w-full"
              size="lg"
            >
              {mutation.isPending ? (
                <>
                  <Spinner size="sm" />
                  Saving…
                </>
              ) : (
                "Save slip"
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
