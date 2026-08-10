"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createSlip } from "@/lib/api";
import type { SlipCreate } from "@/lib/types";
import { useSlipStore } from "@/store/slip-store";
import {
  formatCurrency,
  formatOdds,
  legLabel,
} from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { X, Trash2, Receipt } from "lucide-react";

interface SlipPanelProps {
  onSlipSaved: () => void;
}

export function SlipPanel({ onSlipSaved }: SlipPanelProps) {
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
      currency: "USD",
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
      <div className="flex items-center justify-between border-b border-[#F3F4F6] px-4 py-3.5">
        <div className="flex items-center gap-2">
          <Receipt size={15} className="text-[#6C47FF]" />
          <span className="text-sm font-semibold text-[#111827]">
            Bet Slip
          </span>
          {legs.length > 0 && (
            <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[#6C47FF] px-1.5 text-[10px] font-bold text-white">
              {legs.length}
            </span>
          )}
        </div>
        {legs.length > 0 && (
          <button
            onClick={clearLegs}
            className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-[#9CA3AF] transition-colors duration-150 hover:bg-[#FEE2E2]/60 hover:text-[#DC2626]"
          >
            <Trash2 size={11} />
            Clear
          </button>
        )}
      </div>

      {legs.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2.5 px-4 py-12 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#F3F4F6]">
            <Receipt size={18} className="text-[#9CA3AF]" />
          </div>
          <p className="text-sm font-medium text-[#6B7280]">Slip is empty</p>
          <p className="text-xs text-[#9CA3AF]">
            Pick an outcome from any match to start building
          </p>
        </div>
      ) : (
        <div className="flex flex-col">
          <div className="flex flex-col divide-y divide-[#F3F4F6]">
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
                  <div className="min-w-0 flex flex-col gap-0.5">
                    <span className="truncate text-[11px] text-[#9CA3AF]">
                      {leg.home_team} vs {leg.away_team}
                    </span>
                    <span className="text-sm font-medium leading-tight text-[#111827]">
                      {label}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-sm font-bold tabular-nums text-[#6C47FF]">
                      {formatOdds(leg.price)}
                    </span>
                    <button
                      onClick={() => removeLeg(leg.key)}
                      className="rounded-md p-1 text-[#D1D5DB] transition-colors duration-150 hover:bg-[#FEE2E2]/50 hover:text-[#DC2626]"
                      aria-label="Remove leg"
                    >
                      <X size={13} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="border-t border-[#F3F4F6] bg-[#FAFAFA] p-4 flex flex-col gap-3.5">
            <div className="flex items-center justify-between rounded-xl bg-[#EEE9FF] px-3.5 py-2.5">
              <span className="text-xs font-medium text-[#6C47FF]/70">
                Combined odds
              </span>
              <span className="text-base font-bold tabular-nums text-[#6C47FF]">
                {formatOdds(computedOdds)}
              </span>
            </div>

            <div>
              <label
                htmlFor="stake"
                className="mb-1.5 block text-xs font-medium text-[#6B7280]"
              >
                Stake (USD)
              </label>
              <input
                id="stake"
                type="number"
                min={0.01}
                step={0.01}
                value={stake}
                onChange={(e) => setStake(e.target.value)}
                className="w-full rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-sm tabular-nums text-[#111827] placeholder:text-[#9CA3AF] transition-colors duration-150 focus:border-[#6C47FF] focus:outline-none focus:ring-2 focus:ring-[#6C47FF]/20"
                placeholder="10.00"
              />
            </div>

            {stakeNum > 0 && (
              <div className="flex flex-col gap-1.5 rounded-xl border border-[#E5E7EB] bg-white p-3 text-xs">
                <div className="flex items-center justify-between text-[#6B7280]">
                  <span>Potential return</span>
                  <span className="font-semibold tabular-nums text-[#111827]">
                    {formatCurrency(potentialReturn)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[#6B7280]">
                  <span>Potential profit</span>
                  <span
                    className={`font-semibold tabular-nums ${
                      potentialProfit >= 0 ? "text-[#059669]" : "text-[#DC2626]"
                    }`}
                  >
                    {formatCurrency(potentialProfit)}
                  </span>
                </div>
              </div>
            )}

            <div>
              <label
                htmlFor="slip-name"
                className="mb-1.5 block text-xs font-medium text-[#6B7280]"
              >
                Slip name <span className="text-[#9CA3AF]">(optional)</span>
              </label>
              <input
                id="slip-name"
                type="text"
                value={slipName}
                onChange={(e) => setSlipName(e.target.value)}
                className="w-full rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#111827] placeholder:text-[#9CA3AF] transition-colors duration-150 focus:border-[#6C47FF] focus:outline-none focus:ring-2 focus:ring-[#6C47FF]/20"
                placeholder="My weekend slip"
              />
            </div>

            {saveError && (
              <p className="rounded-lg bg-[#FEE2E2]/60 px-3 py-2 text-xs text-[#DC2626]">
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
