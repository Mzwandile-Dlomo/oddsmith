"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import { fetchDailyAcca, createSlip } from "@/lib/api";
import type { DailyAccaView, MarketType } from "@/lib/types";
import { Spinner } from "@/components/ui/Spinner";
import { formatKickoffShort } from "@/lib/utils";

const TARGET_OPTIONS = [1.3, 1.5, 2.0, 3.0] as const;
const BANKROLL_OPTIONS = [100, 500, 1000] as const;
const HORIZON_DAYS = 30;
const MAX_LEGS = 4;
const MARKET_OPTIONS: { type: MarketType; label: string }[] = [
  { type: "match_winner", label: "Straight win" },
  { type: "over_under", label: "Goals O/U 2.5" },
  { type: "btts", label: "Both teams score" },
];

function odds(v: number) {
  return v.toFixed(2);
}

function pct(v: number) {
  return `${Math.round(v * 100)}%`;
}

function money(v: number) {
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function signedPct(v: number) {
  const p = (v * 100).toFixed(1);
  return v >= 0 ? `+${p}%` : `${p}%`;
}

function marketLabel(marketType: string): string {
  if (marketType === "match_winner") return "1X2";
  if (marketType === "btts") return "BTTS";
  if (marketType === "over_under") return "O/U";
  return marketType;
}

function selectionLabel(marketType: string, selection: string): string {
  if (marketType === "match_winner") {
    if (selection === "Home") return "Home Win";
    if (selection === "Away") return "Away Win";
    return "Draw";
  }
  if (marketType === "btts") return `BTTS: ${selection}`;
  return selection;
}

function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "accent" | "good" | "bad";
}) {
  const toneClass =
    tone === "accent"
      ? "text-accent"
      : tone === "good"
        ? "text-success"
        : tone === "bad"
          ? "text-danger"
          : "text-ink";
  return (
    <div className="min-w-0 rounded-xl border border-border bg-surface px-3 py-3 text-center shadow-subtle sm:px-4">
      <p className="text-[10px] font-medium uppercase tracking-widest text-faint">
        {label}
      </p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}

function StakingPanel({ data }: { data: DailyAccaView }) {
  const s = data.staking;
  const hasEdge = s.recommended_stake > 0;

  if (data.execution_mode === "paper") {
    return (
      <div className="rounded-xl border border-warn-line bg-warn-faint p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-warn" />
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-warn-strong">Paper mode · stake 0</p>
              {data.validation_model && (
                <span className="rounded-full border border-warn-line bg-surface px-2 py-0.5 text-[10px] font-medium text-warn-strong">
                  {data.validation_model}
                </span>
              )}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-warn-deep">
              {data.validation_status} The slip can be saved and tracked, but Oddsmith will
              not recommend real money while the promotion gates fail.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-raised">
      <div className="flex items-center gap-2 border-b border-border bg-subtle px-4 py-3">
        <ShieldCheck className="h-4 w-4 text-accent" />
        <p className="text-[10px] font-semibold uppercase tracking-widest text-muted">
          Stake sizing
        </p>
      </div>

      {/* Back to 2x2 at 2xl: there the panel shares the row with the ticket. */}
      <div className="grid grid-cols-2 gap-px bg-hairline sm:grid-cols-4 2xl:grid-cols-2">
        <div className="bg-surface px-4 py-3">
          <p className="text-[10px] uppercase tracking-widest text-faint">Stake today</p>
          <p className="mt-1 text-lg font-bold tabular-nums text-ink">
            {money(s.recommended_stake)}
          </p>
          <p className="text-[11px] text-faint">{pct(s.recommended_fraction)} of bankroll</p>
        </div>
        <div className="bg-surface px-4 py-3">
          <p className="text-[10px] uppercase tracking-widest text-faint">Growth / day</p>
          <p
            className={`mt-1 text-lg font-bold tabular-nums ${
              s.growth_per_bet > 0 ? "text-success" : "text-muted"
            }`}
          >
            {signedPct(s.growth_per_bet)}
          </p>
          <p className="text-[11px] text-faint">expected, compounding</p>
        </div>
        <div className="bg-surface px-4 py-3">
          <p className="text-[10px] uppercase tracking-widest text-faint">
            After {s.horizon_bets}d
          </p>
          <p className="mt-1 text-lg font-bold tabular-nums text-ink">
            {money(s.projected_bankroll)}
          </p>
          <p className="text-[11px] text-faint">from {money(s.bankroll)}</p>
        </div>
        <div className="bg-surface px-4 py-3">
          <p className="text-[10px] uppercase tracking-widest text-faint">Double in</p>
          <p className="mt-1 text-lg font-bold tabular-nums text-ink">
            {s.bets_to_double === null ? "—" : `${Math.ceil(s.bets_to_double)}d`}
          </p>
          <p className="text-[11px] text-faint">
            {s.bets_to_double === null ? "no edge" : "at this edge"}
          </p>
        </div>
      </div>

      {/* The part people skip. Keep it loud. */}
      <div className="border-t border-warn-line bg-warn-faint px-4 py-3.5">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <div className="flex flex-col gap-1.5">
            <p className="text-xs font-semibold text-warn-strong">
              Why you cannot just let it ride
            </p>
            <p className="text-[12px] leading-relaxed text-warn-deep">
              Staking the <strong>whole bankroll</strong> on a {odds(data.combined_odds)} slip
              every day ends at <strong>{money(s.let_it_ride_bankroll)}</strong> — not because
              the picks are bad, but because one loss takes everything and over{" "}
              {s.horizon_bets} days a loss is near-certain. The model puts the chance of
              winning all {s.horizon_bets} at{" "}
              <strong>{(s.prob_all_win_over_horizon * 100).toFixed(2)}%</strong>, and expects
              about <strong>{s.expected_losses_over_horizon.toFixed(1)}</strong> losing days.
            </p>
            <p className="text-[12px] leading-relaxed text-warn-deep">
              The figures above stake a fixed <em>fraction</em> instead (half-Kelly), which is
              what turns an edge into compounding rather than ruin.
            </p>
            {!hasEdge && (
              <p className="mt-0.5 text-[12px] font-medium leading-relaxed text-warn-strong">
                {s.note}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface DailyResultsProps {
  data: DailyAccaView;
  onSave: () => void;
  isSaving: boolean;
  savedOk: boolean;
  saveError: string | null;
}

function DailyResults({ data, onSave, isSaving, savedOk, saveError }: DailyResultsProps) {
  if (data.legs.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-canvas px-5 py-10 text-center">
        <CalendarDays className="mx-auto mb-3 h-8 w-8 text-outline" />
        <p className="text-sm font-medium text-muted">No slip today</p>
        <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-faint">
          {data.note}
        </p>
        <p className="mt-3 text-[11px] text-faint">
          {data.fixtures_scanned} fixtures scanned · {data.candidates_scanned} value candidates
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[11px] text-faint">
        {data.fixtures_scanned} fixtures scanned · {data.candidates_scanned} value candidates ·{" "}
        {data.pool_size} passed safety filters
      </p>
      {!data.target_met && (
        <div className="rounded-xl border border-warn-line bg-warn-faint px-4 py-3 text-[12px] leading-relaxed text-warn-deep">
          {data.note}
        </div>
      )}

      {/*
        The ticket and the staking plan are two separate reads. From `2xl` the
        results column is wide enough to show both at once rather than pushing
        stake sizing — the part people skip — below the fold.
      */}
      <div className="flex flex-col gap-4 2xl:grid 2xl:grid-cols-2 2xl:items-start 2xl:gap-5">
        <div className="flex min-w-0 flex-col gap-4">
          <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-raised">
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-border bg-subtle px-4 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">
                {data.legs.length}-Leg Daily Slip
              </p>
              <p className="text-[10px] font-medium uppercase tracking-widest text-faint">
                {data.execution_mode === "paper" ? "Paper ticket" : "Live eligible"} · Target {odds(data.target_odds)}
              </p>
            </div>
            <div className="divide-y divide-hairline">
              {data.legs.map((leg, i) => (
                <div key={i} className="flex flex-col gap-1.5 px-4 py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-ink">
                      {leg.home_team} vs {leg.away_team}
                    </p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      <span className="rounded bg-hairline px-1.5 py-0.5 text-[10px] font-medium text-muted">
                        {marketLabel(leg.market_type)}
                      </span>
                      <span className="text-[12px] font-semibold text-accent">
                        {selectionLabel(leg.market_type, leg.selection)}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-faint">
                      {[leg.league, leg.kickoff_utc ? formatKickoffShort(leg.kickoff_utc) : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-baseline gap-x-2 sm:flex-col sm:items-end sm:gap-0.5">
                    <span className="text-[15px] font-bold tabular-nums text-ink">
                      {odds(leg.offered_odds)}
                    </span>
                    <span className="text-[11px] tabular-nums text-faint">
                      Model: {pct(leg.model_prob)}
                    </span>
                    <span className="text-[11px] font-medium tabular-nums text-success">
                      Edge {signedPct(leg.edge)} · EV {signedPct(leg.expected_value)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 min-[420px]:grid-cols-3 sm:gap-3">
            <Stat label="Combined" value={odds(data.combined_odds)} />
            <Stat label="Chance to land" value={pct(data.combined_model_prob)} tone="accent" />
            <Stat
              label="Edge (EV)"
              value={signedPct(data.combined_expected_value)}
              tone={data.combined_expected_value >= 0 ? "good" : "bad"}
            />
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <StakingPanel data={data} />

          {savedOk || data.auto_tracked ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-success-soft bg-success-faint px-4 py-3">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 shrink-0 text-success" />
                <p className="text-sm font-medium text-success-deeper">
                  {data.auto_tracked
                    ? "Automatically recorded for outcome tracking"
                    : "Saved for outcome tracking"}
                </p>
              </div>
              {data.legs[0]?.kickoff_utc && (
                <Link
                  href={`/calendar/${data.legs[0].kickoff_utc.slice(0, 10)}`}
                  className="text-xs font-semibold text-success-deeper underline decoration-success/40 underline-offset-2 hover:decoration-success"
                >
                  Mark the result
                </Link>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <button
                onClick={onSave}
                disabled={isSaving}
                className="flex min-h-[48px] items-center justify-center gap-2 rounded-xl border border-accent bg-accent-light px-5 sm:min-h-[44px] text-sm font-semibold text-accent transition-all duration-150 hover:bg-accent-line focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSaving ? (
                  <>
                    <Spinner size="sm" />
                    Saving…
                  </>
                ) : (
                  data.execution_mode === "paper"
                    ? "Save paper ticket"
                    : `Save at stake ${money(data.staking.recommended_stake)}`
                )}
              </button>
              {saveError && (
                <p className="rounded-xl border border-danger-soft bg-danger-faint px-4 py-2.5 text-sm text-danger">
                  {saveError}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface DailyAccaProps {
  /** ISO date (YYYY-MM-DD) to scope the slip to. Omit for the next 24 hours. */
  date?: string;
  /** Build immediately instead of waiting for the Generate click. */
  autoLoad?: boolean;
  /** Archive the untouched 1.50 daily prediction as a paper ticket. */
  autoTrack?: boolean;
}

export function DailyAcca({
  date,
  autoLoad = false,
  autoTrack = false,
}: DailyAccaProps = {}) {
  const [targetOdds, setTargetOdds] = useState<number>(1.5);
  const [bankroll, setBankroll] = useState<number>(100);
  const [markets, setMarkets] = useState<MarketType[]>(MARKET_OPTIONS.map((m) => m.type));
  const [enabled, setEnabled] = useState(autoLoad);
  const [savedOk, setSavedOk] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const dailyQuery = useQuery<DailyAccaView>({
    queryKey: ["daily-acca", date ?? "next24h", targetOdds, bankroll, markets, autoTrack],
    queryFn: () =>
      fetchDailyAcca({
        targetOdds,
        maxLegs: MAX_LEGS,
        bankroll,
        horizonBets: HORIZON_DAYS,
        markets,
        date,
        autoTrack,
      }),
    enabled,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!dailyQuery.data?.auto_tracked) return;
    queryClient.invalidateQueries({ queryKey: ["slips"] });
    queryClient.invalidateQueries({ queryKey: ["calendar"] });
  }, [dailyQuery.data?.auto_tracked, queryClient]);

  const saveMutation = useMutation({
    mutationFn: createSlip,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["slips"] });
      setSavedOk(true);
      setSaveError(null);
    },
    onError: (err: Error) => setSaveError(err.message),
  });

  function handleGenerate() {
    setEnabled(true);
    setSavedOk(false);
    setSaveError(null);
    if (dailyQuery.isSuccess || dailyQuery.isError) {
      void dailyQuery.refetch();
    }
  }

  function toggleMarket(market: MarketType) {
    setMarkets((current) =>
      current.includes(market)
        ? current.filter((item) => item !== market)
        : [...current, market]
    );
    setSavedOk(false);
  }

  function handleSave() {
    const data = dailyQuery.data;
    if (!data || data.legs.length === 0) return;

    setSavedOk(false);
    setSaveError(null);
    saveMutation.mutate({
      name: `${data.execution_mode === "paper" ? "Paper" : "Daily"} ${data.combined_odds.toFixed(2)} (${data.legs.length}x)${date ? ` · ${date}` : ""}`,
      // Stake what the plan says, not the whole bankroll.
      stake: data.staking.recommended_stake,
      currency: "USD",
      legs: data.legs.map((l) => ({
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
    /*
      Controls beside the ticket from `xl`, where there is room for both. The
      settings are short and fixed-height, so they sit in a sticky rail and the
      slip itself takes the width it deserves instead of everything queueing up
      in one 42rem column with half the page empty.
    */
    <div className="grid w-full grid-cols-1 items-start gap-5 xl:grid-cols-[20rem_minmax(0,1fr)] xl:gap-6 2xl:grid-cols-[22rem_minmax(0,1fr)]">
      <div className="mx-auto w-full max-w-2xl rounded-2xl border border-border bg-surface p-5 shadow-panel xl:mx-0 xl:sticky xl:top-6">
        <div className="mb-4">
          <div className="mb-1 flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold text-ink">Daily Slip</h2>
          </div>
          <p className="text-xs text-faint">
            The slip most likely to land that still clears your target price — plus how much
            to stake so it compounds.
          </p>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-faint">
              Target odds
            </p>
            <div className="flex gap-2">
              {TARGET_OPTIONS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTargetOdds(t)}
                  className={`h-11 w-14 rounded-lg border text-sm font-semibold sm:h-9 transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
                    targetOdds === t
                      ? "border-accent/40 bg-accent-light text-accent ring-1 ring-accent/20"
                      : "border-border bg-surface text-ink-soft hover:border-outline hover:bg-subtle"
                  }`}
                >
                  {t.toFixed(2)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-faint">
              Betting markets
            </p>
            <div className="flex flex-wrap gap-2">
              {MARKET_OPTIONS.map(({ type, label }) => {
                const active = markets.includes(type);
                return (
                  <button
                    key={type}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleMarket(type)}
                    className={`h-11 rounded-lg border px-3 text-xs font-semibold sm:h-9 transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
                      active
                        ? "border-accent/40 bg-accent-light text-accent ring-1 ring-accent/20"
                        : "border-border bg-surface text-muted hover:border-outline"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
              <span
                className="flex h-11 cursor-not-allowed items-center rounded-lg border border-dashed border-outline bg-subtle px-3 sm:h-9 text-xs font-medium text-faint"
                title="Corner count model exists; price history is still too small for ticket use"
              >
                Corners · collecting prices
              </span>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-faint">
              The corner count model is walk-forward tested, but only a few priced fixtures
              exist. It stays disabled until the price-based sample can validate ROI.
            </p>
          </div>

          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-faint">
              Bankroll
            </p>
            <div className="flex gap-2">
              {BANKROLL_OPTIONS.map((b) => (
                <button
                  key={b}
                  onClick={() => setBankroll(b)}
                  className={`h-11 w-16 rounded-lg border text-sm font-semibold sm:h-9 transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
                    bankroll === b
                      ? "border-accent/40 bg-accent-light text-accent ring-1 ring-accent/20"
                      : "border-border bg-surface text-ink-soft hover:border-outline hover:bg-subtle"
                  }`}
                >
                  {b}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={dailyQuery.isFetching || markets.length === 0}
            className="flex min-h-[48px] items-center justify-center gap-2 rounded-xl bg-accent px-5 sm:min-h-[44px] text-sm font-semibold text-white transition-all duration-150 hover:bg-accent-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {dailyQuery.isFetching ? (
              <>
                <Spinner size="sm" />
                Building…
              </>
            ) : (
              <>
                <TrendingUp className="h-4 w-4" />
                Build {targetOdds.toFixed(2)} Slip
              </>
            )}
          </button>
        </div>
      </div>

      <div className="mx-auto flex w-full min-w-0 max-w-2xl flex-col gap-4 xl:mx-0 xl:max-w-none">
        {dailyQuery.isError && (
          <div className="rounded-xl border border-danger-soft bg-danger-faint px-4 py-3 text-sm text-danger">
            {dailyQuery.error instanceof Error
              ? dailyQuery.error.message
              : "Failed to build today's slip. Please try again."}
          </div>
        )}

        {dailyQuery.isSuccess && (
          <DailyResults
            data={dailyQuery.data}
            onSave={handleSave}
            isSaving={saveMutation.isPending}
            savedOk={savedOk}
            saveError={saveError}
          />
        )}

        {!enabled && (
          <div className="rounded-xl border border-dashed border-border px-5 py-12 text-center">
            <CalendarDays className="mx-auto mb-3 h-8 w-8 text-outline" />
            <p className="text-sm text-faint">
              Pick a target price and bankroll, then build today&apos;s slip.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
