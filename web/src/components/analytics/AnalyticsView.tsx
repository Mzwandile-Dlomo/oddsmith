"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { fetchPaperPerformance, fetchSlips } from "@/lib/api";
import type { MarketType, PaperCalibrationView, SlipView } from "@/lib/types";
import { formatOdds, formatPercent, formatSignedCurrency, marketLabel } from "@/lib/utils";
import { PnlChart } from "@/components/charts/PnlChart";
import { Stat, StatGrid, signTone } from "@/components/ui/Stat";
import { SpinnerOverlay } from "@/components/ui/Spinner";

interface MarketRow {
  market: string;
  won: number;
  settled: number;
}

/** Leg-level hit rate per market, counting only legs that won or lost. */
function legsByMarket(slips: SlipView[]): MarketRow[] {
  const rows = new Map<string, MarketRow>();
  for (const leg of slips.flatMap((s) => s.legs)) {
    if (leg.result !== "won" && leg.result !== "lost") continue;
    const row = rows.get(leg.market_type) ?? { market: leg.market_type, won: 0, settled: 0 };
    row.settled += 1;
    if (leg.result === "won") row.won += 1;
    rows.set(leg.market_type, row);
  }
  return [...rows.values()].sort((a, b) => b.settled - a.settled);
}

function MarketHitRates({ rows }: { rows: MarketRow[] }) {
  if (rows.length === 0) {
    return <p className="mt-3 text-sm text-muted">No settled legs yet.</p>;
  }
  return (
    <ul className="mt-4 flex flex-col gap-4">
      {rows.map((row) => {
        const rate = row.won / row.settled;
        return (
          <li key={row.market} className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="truncate font-medium text-ink">{marketLabel(row.market as MarketType)}</span>
              <span className="shrink-0 tabular-nums text-ink">
                {formatPercent(rate)}
                <span className="ml-1.5 text-xs text-faint">
                  {row.won}/{row.settled}
                </span>
              </span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-full bg-hairline"
              role="img"
              aria-label={`${marketLabel(row.market as MarketType)}: ${row.won} of ${row.settled} legs won`}
            >
              <div className="h-full rounded-full bg-accent-mid" style={{ width: `${rate * 100}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Profit over a few dozen 1.50 tickets is mostly luck. Calibration asks the
 * sharper question first: when the model says 65%, does it land about 65%?
 */
function ModelCalibration({ calibration }: { calibration: PaperCalibrationView }) {
  const c = calibration;
  const rows = c.buckets.filter((b) => b.legs > 0);
  return (
    <section className="rounded-2xl border border-border bg-surface p-5 shadow-card">
      <h2 className="text-base font-semibold text-ink">Does it know what it says it knows?</h2>
      <p className="mt-1 text-xs text-muted">
        Each paper leg stores the model&apos;s probability when the ticket is saved. Here it is graded
        against what happened.
      </p>

      <dl className="mt-4 grid grid-cols-1 gap-3 text-sm min-[420px]:grid-cols-2">
        <div>
          <dt className="text-xs text-faint">Legs landed</dt>
          <dd className="tabular-nums text-ink">
            {c.actual_hits} of {c.graded_legs}
            <span className="ml-1.5 text-xs text-faint">
              model expected {c.expected_hits.toFixed(1)}
              {c.graded_legs > 0 &&
                ` (honest range ${c.expected_hits_low.toFixed(1)}–${c.expected_hits_high.toFixed(1)})`}
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-faint">Tickets won</dt>
          <dd className="tabular-nums text-ink">
            {c.actual_ticket_wins} of {c.graded_tickets}
            <span className="ml-1.5 text-xs text-faint">
              model expected {c.expected_ticket_wins.toFixed(1)}
            </span>
          </dd>
        </div>
      </dl>

      {rows.length > 0 && (
        <ul className="mt-5 flex flex-col gap-4">
          {rows.map((b) => {
            const said = b.predicted_rate ?? 0;
            const landed = b.actual_rate ?? 0;
            return (
              <li key={b.label} className="flex flex-col gap-1.5">
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-medium text-ink">Rated {b.label}</span>
                  <span className="shrink-0 tabular-nums text-ink">
                    landed {formatPercent(landed)}
                    <span className="ml-1.5 text-xs text-faint">
                      said {formatPercent(said)} · {b.legs} {b.legs === 1 ? "leg" : "legs"}
                    </span>
                  </span>
                </div>
                <div
                  className="relative h-2 rounded-full bg-hairline"
                  role="img"
                  aria-label={`Rated ${b.label}: model said ${formatPercent(said)}, ${formatPercent(landed)} landed over ${b.legs} legs`}
                >
                  <div className="h-full rounded-full bg-accent-mid" style={{ width: `${landed * 100}%` }} />
                  {/* The tick is what the model claimed; the bar is what happened. */}
                  <div
                    className="absolute -top-1 h-4 w-0.5 rounded-full bg-ink"
                    style={{ left: `calc(${said * 100}% - 1px)` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <p className="mt-4 text-xs leading-relaxed text-muted">
        {c.verdict}
        {c.ungraded_legs > 0 &&
          ` ${c.ungraded_legs} older ${c.ungraded_legs === 1 ? "leg was" : "legs were"} saved before probabilities were stored and ${c.ungraded_legs === 1 ? "is" : "are"} left out.`}
      </p>
    </section>
  );
}

export function AnalyticsView() {
  const slipsQuery = useQuery({ queryKey: ["slips"], queryFn: fetchSlips });
  const paperQuery = useQuery({ queryKey: ["paper-performance"], queryFn: fetchPaperPerformance });

  const slips = useMemo(() => slipsQuery.data ?? [], [slipsQuery.data]);
  const markets = useMemo(() => legsByMarket(slips), [slips]);

  if (slipsQuery.isLoading) return <SpinnerOverlay label="Loading your results…" />;
  if (slipsQuery.isError) {
    return (
      <p className="rounded-xl border border-danger-line bg-danger-faint px-4 py-3 text-sm text-danger">
        Could not load slips. Is the backend running?
      </p>
    );
  }

  const currency = slips[0]?.currency ?? "ZAR";
  const settled = slips.filter((s) => s.result !== "pending");
  const won = settled.filter((s) => s.result === "won").length;
  const staked = settled.reduce((acc, s) => acc + s.stake, 0);
  const pnl = settled.reduce((acc, s) => acc + s.profit_loss, 0);
  const avgOdds = settled.length
    ? settled.reduce((acc, s) => acc + s.combined_odds, 0) / settled.length
    : null;
  const paper = paperQuery.data;

  return (
    <div className="flex flex-col gap-6">
      <StatGrid min="10rem">
        <Stat
          label="Net profit / loss"
          value={settled.length ? formatSignedCurrency(pnl, currency) : "—"}
          tone={signTone(pnl)}
          size="lg"
        />
        <Stat label="Staked" value={`${currency} ${staked.toFixed(2)}`} size="lg" />
        <Stat
          label="Return on stake"
          value={staked > 0 ? `${pnl >= 0 ? "+" : ""}${formatPercent(pnl / staked, 1)}` : "—"}
          tone={staked > 0 ? signTone(pnl) : "default"}
          size="lg"
        />
        <Stat
          label="Hit rate"
          value={settled.length ? formatPercent(won / settled.length) : "—"}
          detail={`${won} of ${settled.length} slips`}
          size="lg"
        />
        <Stat label="Average odds" value={avgOdds === null ? "—" : formatOdds(avgOdds)} size="lg" />
      </StatGrid>

      <section className="rounded-2xl border border-border bg-surface p-5 shadow-card">
        <h2 className="text-base font-semibold text-ink">Profit over time</h2>
        <p className="mb-4 mt-1 text-xs text-muted">
          Running total after each settled slip. Paper tickets have no stake, so they add nothing here.
        </p>
        <PnlChart slips={slips} currency={currency} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-border bg-surface p-5 shadow-card">
          <h2 className="text-base font-semibold text-ink">Leg hit rate by market</h2>
          <p className="mt-1 text-xs text-muted">Every leg you settled, across all slips.</p>
          <MarketHitRates rows={markets} />
        </section>

        <section className="rounded-2xl border border-border bg-surface p-5 shadow-card">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-ink">Model paper track</h2>
            <Link
              href="/model"
              className="flex min-h-[40px] items-center gap-1 rounded-lg px-2 text-sm text-muted transition-colors hover:text-accent sm:min-h-[32px]"
            >
              Model <ChevronRight size={15} />
            </Link>
          </div>
          {paper ? (
            <>
              <div className="mt-4 flex items-baseline justify-between gap-3 text-sm">
                <span className="text-muted">Tickets settled</span>
                <span className="tabular-nums text-ink">
                  {paper.settled_tickets} / {paper.tracking_target}
                </span>
              </div>
              <div
                className="mt-1.5 h-2 overflow-hidden rounded-full bg-hairline"
                role="img"
                aria-label={`${paper.settled_tickets} of ${paper.tracking_target} paper tickets settled`}
              >
                <div
                  className="h-full rounded-full bg-info"
                  style={{ width: `${Math.min(paper.settled_tickets / paper.tracking_target, 1) * 100}%` }}
                />
              </div>
              <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
                <div>
                  <dt className="text-xs text-faint">Won</dt>
                  <dd className="tabular-nums text-ink">{paper.won_tickets}</dd>
                </div>
                <div>
                  <dt className="text-xs text-faint">Unit profit</dt>
                  <dd className="tabular-nums text-ink">{paper.unit_profit.toFixed(2)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-faint">Unit ROI</dt>
                  <dd className="tabular-nums text-ink">
                    {paper.unit_roi === null ? "—" : formatPercent(paper.unit_roi, 1)}
                  </dd>
                </div>
              </dl>
              <p className="mt-4 text-xs leading-relaxed text-muted">{paper.note}</p>
            </>
          ) : (
            <p className="mt-3 text-sm text-muted">Loading paper performance…</p>
          )}
        </section>
      </div>

      {paper && <ModelCalibration calibration={paper.calibration} />}
    </div>
  );
}
