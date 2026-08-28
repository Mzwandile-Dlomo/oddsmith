"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
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
      ? "text-[#6C47FF]"
      : tone === "good"
        ? "text-[#059669]"
        : tone === "bad"
          ? "text-[#DC2626]"
          : "text-[#111827]";
  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white px-4 py-3 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <p className="text-[10px] font-medium uppercase tracking-widest text-[#9CA3AF]">
        {label}
      </p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}

function StakingPanel({ data }: { data: DailyAccaView }) {
  const s = data.staking;
  const hasEdge = s.recommended_stake > 0;

  return (
    <div className="overflow-hidden rounded-xl border border-[#E5E7EB] bg-white shadow-[0_1px_4px_rgba(0,0,0,0.06)]">
      <div className="flex items-center gap-2 border-b border-[#E5E7EB] bg-[#F9FAFB] px-4 py-3">
        <ShieldCheck className="h-4 w-4 text-[#6C47FF]" />
        <p className="text-[10px] font-semibold uppercase tracking-widest text-[#6B7280]">
          Stake sizing
        </p>
      </div>

      <div className="grid grid-cols-2 gap-px bg-[#F3F4F6] sm:grid-cols-4">
        <div className="bg-white px-4 py-3">
          <p className="text-[10px] uppercase tracking-widest text-[#9CA3AF]">Stake today</p>
          <p className="mt-1 text-lg font-bold tabular-nums text-[#111827]">
            {money(s.recommended_stake)}
          </p>
          <p className="text-[11px] text-[#9CA3AF]">{pct(s.recommended_fraction)} of bankroll</p>
        </div>
        <div className="bg-white px-4 py-3">
          <p className="text-[10px] uppercase tracking-widest text-[#9CA3AF]">Growth / day</p>
          <p
            className={`mt-1 text-lg font-bold tabular-nums ${
              s.growth_per_bet > 0 ? "text-[#059669]" : "text-[#6B7280]"
            }`}
          >
            {signedPct(s.growth_per_bet)}
          </p>
          <p className="text-[11px] text-[#9CA3AF]">expected, compounding</p>
        </div>
        <div className="bg-white px-4 py-3">
          <p className="text-[10px] uppercase tracking-widest text-[#9CA3AF]">
            After {s.horizon_bets}d
          </p>
          <p className="mt-1 text-lg font-bold tabular-nums text-[#111827]">
            {money(s.projected_bankroll)}
          </p>
          <p className="text-[11px] text-[#9CA3AF]">from {money(s.bankroll)}</p>
        </div>
        <div className="bg-white px-4 py-3">
          <p className="text-[10px] uppercase tracking-widest text-[#9CA3AF]">Double in</p>
          <p className="mt-1 text-lg font-bold tabular-nums text-[#111827]">
            {s.bets_to_double === null ? "—" : `${Math.ceil(s.bets_to_double)}d`}
          </p>
          <p className="text-[11px] text-[#9CA3AF]">
            {s.bets_to_double === null ? "no edge" : "at this edge"}
          </p>
        </div>
      </div>

      {/* The part people skip. Keep it loud. */}
      <div className="border-t border-[#FDE68A] bg-[#FFFBEB] px-4 py-3.5">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#D97706]" />
          <div className="flex flex-col gap-1.5">
            <p className="text-xs font-semibold text-[#92400E]">
              Why you cannot just let it ride
            </p>
            <p className="text-[12px] leading-relaxed text-[#78350F]">
              Staking the <strong>whole bankroll</strong> on a {odds(data.combined_odds)} slip
              every day ends at <strong>{money(s.let_it_ride_bankroll)}</strong> — not because
              the picks are bad, but because one loss takes everything and over{" "}
              {s.horizon_bets} days a loss is near-certain. The model puts the chance of
              winning all {s.horizon_bets} at{" "}
              <strong>{(s.prob_all_win_over_horizon * 100).toFixed(2)}%</strong>, and expects
              about <strong>{s.expected_losses_over_horizon.toFixed(1)}</strong> losing days.
            </p>
            <p className="text-[12px] leading-relaxed text-[#78350F]">
              The figures above stake a fixed <em>fraction</em> instead (half-Kelly), which is
              what turns an edge into compounding rather than ruin.
            </p>
            {!hasEdge && (
              <p className="mt-0.5 text-[12px] font-medium leading-relaxed text-[#92400E]">
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
      <div className="rounded-xl border border-[#E5E7EB] bg-[#FAFAFA] px-5 py-10 text-center">
        <CalendarDays className="mx-auto mb-3 h-8 w-8 text-[#D1D5DB]" />
        <p className="text-sm font-medium text-[#6B7280]">No slip today</p>
        <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-[#9CA3AF]">
          {data.note}
        </p>
        <p className="mt-3 text-[11px] text-[#9CA3AF]">
          {data.fixtures_scanned} fixtures scanned · {data.candidates_scanned} value candidates
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[11px] text-[#9CA3AF]">
        {data.fixtures_scanned} fixtures scanned · {data.candidates_scanned} value candidates ·{" "}
        {data.pool_size} passed safety filters
      </p>
      {!data.target_met && (
        <div className="rounded-xl border border-[#FDE68A] bg-[#FFFBEB] px-4 py-3 text-[12px] leading-relaxed text-[#78350F]">
          {data.note}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-[#E5E7EB] bg-white shadow-[0_1px_4px_rgba(0,0,0,0.06)]">
        <div className="flex items-center justify-between border-b border-[#E5E7EB] bg-[#F9FAFB] px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
            {data.legs.length}-Leg Daily Slip
          </p>
          <p className="text-[10px] font-medium uppercase tracking-widest text-[#9CA3AF]">
            Target {odds(data.target_odds)}
          </p>
        </div>
        <div className="divide-y divide-[#F3F4F6]">
          {data.legs.map((leg, i) => (
            <div key={i} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-[#111827]">
                  {leg.home_team} vs {leg.away_team}
                </p>
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                  <span className="rounded bg-[#F3F4F6] px-1.5 py-0.5 text-[10px] font-medium text-[#6B7280]">
                    {marketLabel(leg.market_type)}
                  </span>
                  <span className="text-[12px] font-semibold text-[#6C47FF]">
                    {selectionLabel(leg.market_type, leg.selection)}
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-0.5">
                <span className="text-[15px] font-bold tabular-nums text-[#111827]">
                  {odds(leg.offered_odds)}
                </span>
                <span className="text-[11px] tabular-nums text-[#9CA3AF]">
                  Model: {pct(leg.model_prob)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Combined" value={odds(data.combined_odds)} />
        <Stat label="Chance to land" value={pct(data.combined_model_prob)} tone="accent" />
        <Stat
          label="Edge (EV)"
          value={signedPct(data.combined_expected_value)}
          tone={data.combined_expected_value >= 0 ? "good" : "bad"}
        />
      </div>

      <StakingPanel data={data} />

      {savedOk ? (
        <div className="flex items-center gap-2 rounded-xl border border-[#D1FAE5] bg-[#ECFDF5] px-4 py-3">
          <CheckCircle className="h-4 w-4 shrink-0 text-[#059669]" />
          <p className="text-sm font-medium text-[#065F46]">Saved to My Slips</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <button
            onClick={onSave}
            disabled={isSaving}
            className="flex h-10 items-center justify-center gap-2 rounded-xl border border-[#6C47FF] bg-[#EEE9FF] px-5 text-sm font-semibold text-[#6C47FF] transition-all duration-150 hover:bg-[#DDD5FF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6C47FF]/40 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving ? (
              <>
                <Spinner size="sm" />
                Saving…
              </>
            ) : (
              `Save at stake ${money(data.staking.recommended_stake)}`
            )}
          </button>
          {saveError && (
            <p className="rounded-xl border border-[#FEE2E2] bg-[#FEF2F2] px-4 py-2.5 text-sm text-[#DC2626]">
              {saveError}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

interface DailyAccaProps {
  /** ISO date (YYYY-MM-DD) to scope the slip to. Omit for the next 24 hours. */
  date?: string;
  /** Build immediately instead of waiting for the Generate click. */
  autoLoad?: boolean;
}

export function DailyAcca({ date, autoLoad = false }: DailyAccaProps = {}) {
  const [targetOdds, setTargetOdds] = useState<number>(1.5);
  const [bankroll, setBankroll] = useState<number>(100);
  const [markets, setMarkets] = useState<MarketType[]>(MARKET_OPTIONS.map((m) => m.type));
  const [enabled, setEnabled] = useState(autoLoad);
  const [savedOk, setSavedOk] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const dailyQuery = useQuery<DailyAccaView>({
    queryKey: ["daily-acca", date ?? "next24h", targetOdds, bankroll, markets],
    queryFn: () =>
      fetchDailyAcca({
        targetOdds,
        maxLegs: MAX_LEGS,
        bankroll,
        horizonBets: HORIZON_DAYS,
        markets,
        date,
      }),
    enabled,
    staleTime: 60_000,
  });

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
      name: `Daily ${data.combined_odds.toFixed(2)} (${data.legs.length}x)${date ? ` · ${date}` : ""}`,
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
    <div className="flex max-w-2xl flex-col gap-6">
      <div className="rounded-2xl border border-[#E5E7EB] bg-white p-5 shadow-[0_4px_16px_rgba(0,0,0,0.06)]">
        <div className="mb-4">
          <div className="mb-1 flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-[#6C47FF]" />
            <h2 className="text-sm font-semibold text-[#111827]">Daily Slip</h2>
          </div>
          <p className="text-xs text-[#9CA3AF]">
            The slip most likely to land that still clears your target price — plus how much
            to stake so it compounds.
          </p>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
              Target odds
            </p>
            <div className="flex gap-2">
              {TARGET_OPTIONS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTargetOdds(t)}
                  className={`h-9 w-14 rounded-lg border text-sm font-semibold transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6C47FF]/40 ${
                    targetOdds === t
                      ? "border-[#6C47FF]/40 bg-[#EEE9FF] text-[#6C47FF] ring-1 ring-[#6C47FF]/20"
                      : "border-[#E5E7EB] bg-white text-[#374151] hover:border-[#D1D5DB] hover:bg-[#F9FAFB]"
                  }`}
                >
                  {t.toFixed(2)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
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
                    className={`h-9 rounded-lg border px-3 text-xs font-semibold transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6C47FF]/40 ${
                      active
                        ? "border-[#6C47FF]/40 bg-[#EEE9FF] text-[#6C47FF] ring-1 ring-[#6C47FF]/20"
                        : "border-[#E5E7EB] bg-white text-[#6B7280] hover:border-[#D1D5DB]"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
              <span
                className="flex h-9 cursor-not-allowed items-center rounded-lg border border-dashed border-[#D1D5DB] bg-[#F9FAFB] px-3 text-xs font-medium text-[#9CA3AF]"
                title="Corner outcomes are loaded; the count model and historical prices are next"
              >
                Corners · model pending
              </span>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-[#9CA3AF]">
              Corner outcomes are loaded, but the market stays disabled until its count model
              and price-based backtest pass validation.
            </p>
          </div>

          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
              Bankroll
            </p>
            <div className="flex gap-2">
              {BANKROLL_OPTIONS.map((b) => (
                <button
                  key={b}
                  onClick={() => setBankroll(b)}
                  className={`h-9 w-16 rounded-lg border text-sm font-semibold transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6C47FF]/40 ${
                    bankroll === b
                      ? "border-[#6C47FF]/40 bg-[#EEE9FF] text-[#6C47FF] ring-1 ring-[#6C47FF]/20"
                      : "border-[#E5E7EB] bg-white text-[#374151] hover:border-[#D1D5DB] hover:bg-[#F9FAFB]"
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
            className="flex h-10 items-center justify-center gap-2 rounded-xl bg-[#6C47FF] px-5 text-sm font-semibold text-white transition-all duration-150 hover:bg-[#5B3AEE] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6C47FF]/40 disabled:cursor-not-allowed disabled:opacity-60"
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

      {dailyQuery.isError && (
        <div className="rounded-xl border border-[#FEE2E2] bg-[#FEF2F2] px-4 py-3 text-sm text-[#DC2626]">
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
        <div className="rounded-xl border border-dashed border-[#E5E7EB] px-5 py-12 text-center">
          <CalendarDays className="mx-auto mb-3 h-8 w-8 text-[#D1D5DB]" />
          <p className="text-sm text-[#9CA3AF]">
            Pick a target price and bankroll, then build today&apos;s slip.
          </p>
        </div>
      )}
    </div>
  );
}
