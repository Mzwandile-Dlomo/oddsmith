"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { TrendingUp, AlertCircle, Info, CheckCircle } from "lucide-react";
import { fetchWeekendAcca, fetchBacktest, createSlip } from "@/lib/api";
import type { AccaView, MarketType } from "@/lib/types";
import { Spinner } from "@/components/ui/Spinner";

const LEG_OPTIONS = [3, 4, 5, 6] as const;
type LegCount = (typeof LEG_OPTIONS)[number];

function formatOdds(v: number) {
  return v.toFixed(2);
}

function formatPct(v: number) {
  return `${Math.round(v * 100)}%`;
}

function formatEdge(v: number) {
  const pct = Math.round(v * 100);
  return pct >= 0 ? `+${pct}%` : `${pct}%`;
}

function selectionLabel(marketType: string, selection: string): string {
  if (marketType === "match_winner") {
    if (selection === "Home") return "Home Win";
    if (selection === "Away") return "Away Win";
    return "Draw";
  }
  if (marketType === "btts") return `BTTS: ${selection}`;
  if (marketType === "over_under") return selection;
  return selection;
}

function marketLabel(marketType: string): string {
  if (marketType === "match_winner") return "1X2";
  if (marketType === "btts") return "BTTS";
  if (marketType === "over_under") return "O/U";
  return marketType;
}

interface AccaResultsProps {
  acca: AccaView;
  hitRate: number | null;
  onSave: () => void;
  isSaving: boolean;
  savedOk: boolean;
  saveError: string | null;
}

function AccaResults({ acca, hitRate, onSave, isSaving, savedOk, saveError }: AccaResultsProps) {
  if (acca.legs.length === 0) {
    return (
      <div className="rounded-xl border border-[#E5E7EB] bg-[#FAFAFA] px-5 py-10 text-center">
        <p className="text-sm text-[#9CA3AF]">
          No value picks found in the current window.
        </p>
        <p className="mt-1 text-xs text-[#9CA3AF]">
          Try again later or reduce the number of legs.
        </p>
      </div>
    );
  }

  const validLegs = acca.legs.filter((l) => l.offered_odds > 1.0);

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-[#E5E7EB] bg-white shadow-[0_1px_4px_rgba(0,0,0,0.06)] overflow-hidden">
        <div className="border-b border-[#E5E7EB] bg-[#F9FAFB] px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
            {acca.legs.length}-Leg Value Accumulator
          </p>
        </div>
        <div className="divide-y divide-[#F3F4F6]">
          {acca.legs.map((leg, i) => (
            <div key={i} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-medium text-[#111827] truncate">
                  {leg.home_team} vs {leg.away_team}
                </p>
                <div className="mt-0.5 flex items-center gap-1.5 flex-wrap">
                  <span className="rounded bg-[#F3F4F6] px-1.5 py-0.5 text-[10px] font-medium text-[#6B7280]">
                    {marketLabel(leg.market_type)}
                  </span>
                  <span className="text-[12px] font-semibold text-[#6C47FF]">
                    {selectionLabel(leg.market_type, leg.selection)}
                  </span>
                </div>
              </div>
              <div className="flex flex-col items-end gap-0.5 shrink-0">
                <span className="text-[15px] font-bold tabular-nums text-[#111827]">
                  {formatOdds(leg.offered_odds)}
                </span>
                <span className="text-[11px] text-[#9CA3AF] tabular-nums">
                  Model: {formatPct(leg.model_prob)}
                </span>
                <span className={`text-[11px] font-semibold tabular-nums ${leg.edge >= 0 ? "text-[#059669]" : "text-[#DC2626]"}`}>
                  Edge {formatEdge(leg.edge)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-[#E5E7EB] bg-white px-4 py-3 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <p className="text-[10px] font-medium uppercase tracking-widest text-[#9CA3AF]">
            Combined Odds
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums text-[#111827]">
            {formatOdds(acca.combined_odds)}
          </p>
        </div>
        <div className="rounded-xl border border-[#E5E7EB] bg-white px-4 py-3 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <p className="text-[10px] font-medium uppercase tracking-widest text-[#9CA3AF]">
            Model Prob
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums text-[#6C47FF]">
            {formatPct(acca.combined_model_prob)}
          </p>
        </div>
        <div className="rounded-xl border border-[#E5E7EB] bg-white px-4 py-3 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <p className="text-[10px] font-medium uppercase tracking-widest text-[#9CA3AF]">
            Expected Value
          </p>
          <p className={`mt-1 text-xl font-bold tabular-nums ${acca.combined_expected_value >= 0 ? "text-[#059669]" : "text-[#DC2626]"}`}>
            +{acca.combined_expected_value.toFixed(1)}%
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {savedOk ? (
          <div className="flex items-center gap-2 rounded-xl border border-[#D1FAE5] bg-[#ECFDF5] px-4 py-3">
            <CheckCircle className="h-4 w-4 shrink-0 text-[#059669]" />
            <p className="text-sm font-medium text-[#065F46]">Saved to My Slips</p>
          </div>
        ) : (
          <>
            <button
              onClick={onSave}
              disabled={isSaving || validLegs.length === 0}
              className="flex h-10 items-center justify-center gap-2 rounded-xl border border-[#6C47FF] bg-[#EEE9FF] px-5 text-sm font-semibold text-[#6C47FF] transition-all duration-150 hover:bg-[#DDD5FF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6C47FF]/40 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? (
                <>
                  <Spinner size="sm" />
                  Saving…
                </>
              ) : (
                "Save to My Slips"
              )}
            </button>
            {saveError && (
              <p className="rounded-xl border border-[#FEE2E2] bg-[#FEF2F2] px-4 py-2.5 text-sm text-[#DC2626]">
                {saveError}
              </p>
            )}
          </>
        )}
      </div>

      <div className="rounded-xl border border-[#E5E7EB] bg-[#F9FAFB] px-4 py-3.5">
        <div className="flex items-start gap-2">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#D97706]" />
          <div className="flex flex-col gap-1">
            <p className="text-xs font-semibold text-[#92400E]">Honest note</p>
            <p className="text-[12px] leading-relaxed text-[#78350F]">
              These are value picks where our model rates the outcome higher than the
              bookmaker. A multi-leg accumulator still lands only a small % of the time
              — this targets long-term expected value, not a guaranteed win.
            </p>
            {hitRate !== null && (
              <p className="mt-1 text-[11px] text-[#9CA3AF]">
                <Info className="mr-1 inline-block h-3 w-3" />
                Model 1X2 accuracy (backtested): ~{Math.round(hitRate * 100)}%
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function OddsGenerator() {
  const [legs, setLegs] = useState<LegCount>(5);
  const [enabled, setEnabled] = useState(false);
  const [queryLegs, setQueryLegs] = useState<LegCount>(5);
  const [savedOk, setSavedOk] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const accaQuery = useQuery<AccaView>({
    queryKey: ["weekend-acca", queryLegs],
    queryFn: () => fetchWeekendAcca(queryLegs),
    enabled,
    staleTime: 60_000,
  });

  const backtestQuery = useQuery({
    queryKey: ["backtest"],
    queryFn: fetchBacktest,
    staleTime: 300_000,
  });

  const saveMutation = useMutation({
    mutationFn: createSlip,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["slips"] });
      setSavedOk(true);
      setSaveError(null);
    },
    onError: (err: Error) => {
      setSaveError(err.message);
    },
  });

  const hitRate = backtestQuery.data?.hit_rate ?? null;

  function handleGenerate() {
    setQueryLegs(legs);
    setEnabled(true);
    setSavedOk(false);
    setSaveError(null);
    if (accaQuery.isSuccess || accaQuery.isError) {
      void accaQuery.refetch();
    }
  }

  function handleSave() {
    if (!accaQuery.data) return;
    const validLegs = accaQuery.data.legs.filter((l) => l.offered_odds > 1.0);
    if (validLegs.length === 0) return;

    setSavedOk(false);
    setSaveError(null);

    saveMutation.mutate({
      name: `Value acca (${validLegs.length}x)`,
      stake: 10,
      currency: "USD",
      legs: validLegs.map((l) => ({
        fixture_id: l.fixture_id,
        home_team: l.home_team,
        away_team: l.away_team,
        kickoff_utc: l.kickoff_utc ?? new Date().toISOString(),
        league: l.league ?? null,
        provider: l.provider,
        market_type: l.market_type as MarketType,
        selection: l.selection,
        point: l.point ?? null,
        price: l.offered_odds,
      })),
    });
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div className="rounded-2xl border border-[#E5E7EB] bg-white p-5 shadow-[0_4px_16px_rgba(0,0,0,0.06)]">
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="h-4 w-4 text-[#6C47FF]" />
            <h2 className="text-sm font-semibold text-[#111827]">Value Acca Generator</h2>
          </div>
          <p className="text-xs text-[#9CA3AF]">
            Auto-build an accumulator from this weekend&apos;s highest-edge picks.
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
              Number of legs
            </p>
            <div className="flex gap-2">
              {LEG_OPTIONS.map((n) => (
                <button
                  key={n}
                  onClick={() => setLegs(n)}
                  className={`h-9 w-12 rounded-lg border text-sm font-semibold transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6C47FF]/40 ${
                    legs === n
                      ? "border-[#6C47FF]/40 bg-[#EEE9FF] text-[#6C47FF] ring-1 ring-[#6C47FF]/20"
                      : "border-[#E5E7EB] bg-white text-[#374151] hover:border-[#D1D5DB] hover:bg-[#F9FAFB]"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={accaQuery.isFetching}
            className="flex h-10 items-center justify-center gap-2 rounded-xl bg-[#6C47FF] px-5 text-sm font-semibold text-white transition-all duration-150 hover:bg-[#5B3AEE] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6C47FF]/40 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {accaQuery.isFetching ? (
              <>
                <Spinner size="sm" />
                Generating…
              </>
            ) : (
              <>
                <TrendingUp className="h-4 w-4" />
                Generate {legs}-Leg Acca
              </>
            )}
          </button>
        </div>
      </div>

      {accaQuery.isError && (
        <div className="rounded-xl border border-[#FEE2E2] bg-[#FEF2F2] px-4 py-3 text-sm text-[#DC2626]">
          Failed to generate accumulator. Please try again.
        </div>
      )}

      {accaQuery.isSuccess && (
        <AccaResults
          acca={accaQuery.data}
          hitRate={hitRate}
          onSave={handleSave}
          isSaving={saveMutation.isPending}
          savedOk={savedOk}
          saveError={saveError}
        />
      )}

      {!enabled && (
        <div className="rounded-xl border border-dashed border-[#E5E7EB] px-5 py-12 text-center">
          <TrendingUp className="mx-auto mb-3 h-8 w-8 text-[#D1D5DB]" />
          <p className="text-sm text-[#9CA3AF]">
            Choose the number of legs and click Generate.
          </p>
        </div>
      )}
    </div>
  );
}
