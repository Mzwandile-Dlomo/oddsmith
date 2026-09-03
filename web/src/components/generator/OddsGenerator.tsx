"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { TrendingUp, AlertCircle, Info, CheckCircle } from "lucide-react";
import { fetchWeekendAcca, fetchBacktest, createSlip } from "@/lib/api";
import type { AccaView, MarketType } from "@/lib/types";
import { Spinner } from "@/components/ui/Spinner";
import { formatSignedPercent } from "@/lib/utils";

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
      <div className="rounded-xl border border-border bg-canvas px-5 py-10 text-center">
        <p className="text-sm text-faint">
          No value picks found in the current window.
        </p>
        <p className="mt-1 text-xs text-faint">
          Try again later or reduce the number of legs.
        </p>
      </div>
    );
  }

  const validLegs = acca.legs.filter((l) => l.offered_odds > 1.0);

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-surface shadow-raised overflow-hidden">
        <div className="border-b border-border bg-subtle px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">
            {acca.legs.length}-Leg Value Accumulator
          </p>
        </div>
        <div className="divide-y divide-hairline">
          {acca.legs.map((leg, i) => (
            <div key={i} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-medium text-ink truncate">
                  {leg.home_team} vs {leg.away_team}
                </p>
                <div className="mt-0.5 flex items-center gap-1.5 flex-wrap">
                  <span className="rounded bg-hairline px-1.5 py-0.5 text-[10px] font-medium text-muted">
                    {marketLabel(leg.market_type)}
                  </span>
                  <span className="text-[12px] font-semibold text-accent">
                    {selectionLabel(leg.market_type, leg.selection)}
                  </span>
                </div>
              </div>
              <div className="flex flex-col items-end gap-0.5 shrink-0">
                <span className="text-[15px] font-bold tabular-nums text-ink">
                  {formatOdds(leg.offered_odds)}
                </span>
                <span className="text-[11px] text-faint tabular-nums">
                  Model: {formatPct(leg.model_prob)}
                </span>
                <span className={`text-[11px] font-semibold tabular-nums ${leg.edge >= 0 ? "text-success" : "text-danger"}`}>
                  Edge {formatEdge(leg.edge)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 min-[420px]:grid-cols-3 sm:gap-3">
        <div className="min-w-0 rounded-xl border border-border bg-surface px-3 py-3 text-center shadow-subtle sm:px-4">
          <p className="text-[10px] font-medium uppercase tracking-widest text-faint">
            Combined Odds
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums text-ink">
            {formatOdds(acca.combined_odds)}
          </p>
        </div>
        <div className="min-w-0 rounded-xl border border-border bg-surface px-3 py-3 text-center shadow-subtle sm:px-4">
          <p className="text-[10px] font-medium uppercase tracking-widest text-faint">
            Model Prob
          </p>
          <p className="mt-1 text-xl font-bold tabular-nums text-accent">
            {formatPct(acca.combined_model_prob)}
          </p>
        </div>
        <div className="min-w-0 rounded-xl border border-border bg-surface px-3 py-3 text-center shadow-subtle sm:px-4">
          <p className="text-[10px] font-medium uppercase tracking-widest text-faint">
            Expected Value
          </p>
          <p className={`mt-1 text-xl font-bold tabular-nums ${acca.combined_expected_value >= 0 ? "text-success" : "text-danger"}`}>
            {formatSignedPercent(acca.combined_expected_value)}
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {savedOk ? (
          <div className="flex items-center gap-2 rounded-xl border border-success-soft bg-success-faint px-4 py-3">
            <CheckCircle className="h-4 w-4 shrink-0 text-success" />
            <p className="text-sm font-medium text-success-deeper">Saved to My Slips</p>
          </div>
        ) : (
          <>
            <button
              onClick={onSave}
              disabled={isSaving || validLegs.length === 0}
              className="flex min-h-[48px] items-center justify-center gap-2 rounded-xl border border-accent bg-accent-light px-5 sm:min-h-[44px] text-sm font-semibold text-accent transition-all duration-150 hover:bg-accent-line focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50 disabled:cursor-not-allowed"
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
              <p className="rounded-xl border border-danger-soft bg-danger-faint px-4 py-2.5 text-sm text-danger">
                {saveError}
              </p>
            )}
          </>
        )}
      </div>

      <div className="rounded-xl border border-border bg-subtle px-4 py-3.5">
        <div className="flex items-start gap-2">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <div className="flex flex-col gap-1">
            <p className="text-xs font-semibold text-warn-strong">Honest note</p>
            <p className="text-[12px] leading-relaxed text-warn-deep">
              These are value picks where our model rates the outcome higher than the
              bookmaker. A multi-leg accumulator still lands only a small % of the time
              — this targets long-term expected value, not a guaranteed win.
            </p>
            {hitRate !== null && (
              <p className="mt-1 text-[11px] text-faint">
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
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 xl:mx-0">
      <div className="rounded-2xl border border-border bg-surface p-5 shadow-panel">
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold text-ink">Value Acca Generator</h2>
          </div>
          <p className="text-xs text-faint">
            Auto-build an accumulator from this weekend&apos;s highest-edge picks.
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-faint">
              Number of legs
            </p>
            <div className="flex gap-2">
              {LEG_OPTIONS.map((n) => (
                <button
                  key={n}
                  onClick={() => setLegs(n)}
                  className={`h-11 w-12 rounded-lg border text-sm font-semibold sm:h-9 transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
                    legs === n
                      ? "border-accent/40 bg-accent-light text-accent ring-1 ring-accent/20"
                      : "border-border bg-surface text-ink-soft hover:border-outline hover:bg-subtle"
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
            className="flex min-h-[48px] items-center justify-center gap-2 rounded-xl bg-accent px-5 sm:min-h-[44px] text-sm font-semibold text-white transition-all duration-150 hover:bg-accent-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-60 disabled:cursor-not-allowed"
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
        <div className="rounded-xl border border-danger-soft bg-danger-faint px-4 py-3 text-sm text-danger">
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
        <div className="rounded-xl border border-dashed border-border px-5 py-12 text-center">
          <TrendingUp className="mx-auto mb-3 h-8 w-8 text-outline" />
          <p className="text-sm text-faint">
            Choose the number of legs and click Generate.
          </p>
        </div>
      )}
    </div>
  );
}
