"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  BrainCircuit,
  CheckCircle2,
  CircleDashed,
  Clock3,
  Database,
  ShieldAlert,
} from "lucide-react";
import {
  fetchLatestCornerEvaluation,
  fetchLatestEvaluation,
  fetchModelReadiness,
  fetchPaperPerformance,
} from "@/lib/api";
import type {
  CornerEvaluationReportView,
  EvaluationReportView,
  MarketReadinessView,
  ModelReadinessView,
  PaperPerformanceView,
} from "@/lib/types";
import { Spinner } from "@/components/ui/Spinner";
import { ScrollArea } from "@/components/ui/ScrollArea";

function number(value: number): string {
  return new Intl.NumberFormat().format(value);
}

function date(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function percent(value: number | null, signed = false): string {
  if (value === null) return "—";
  const rendered = `${(value * 100).toFixed(2)}%`;
  return signed && value > 0 ? `+${rendered}` : rendered;
}

function StageBadge({ stage }: { stage: MarketReadinessView["stage"] }) {
  const styles = {
    baseline: "border-info-line bg-info-faint text-info",
    research: "border-warn-line bg-warn-faint text-warn-strong",
    blocked: "border-border bg-subtle text-muted",
  }[stage];
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${styles}`}>
      {stage}
    </span>
  );
}

function Summary({ data }: { data: ModelReadinessView }) {
  const items = [
    { label: "Enriched matches", value: number(data.dataset_matches), icon: Database },
    { label: "Leagues", value: String(data.leagues), icon: BarChart3 },
    { label: "Seasons", value: String(data.seasons), icon: Clock3 },
    { label: "Price snapshots", value: number(data.price_snapshots), icon: Database },
    {
      label: "Latest result",
      value: date(data.date_to),
      icon: CircleDashed,
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {items.map(({ label, value, icon: Icon }) => (
        <div key={label} className="rounded-xl border border-border bg-surface p-4 shadow-sm">
          <div className="flex items-center gap-2 text-faint">
            <Icon className="h-3.5 w-3.5" />
            <p className="text-[10px] font-semibold uppercase tracking-widest">{label}</p>
          </div>
          <p className="mt-2 text-xl font-bold tracking-tight text-ink">{value}</p>
        </div>
      ))}
    </div>
  );
}

function PaperPerformance({ data }: { data?: PaperPerformanceView }) {
  if (!data) {
    return (
      <section className="rounded-2xl border border-dashed border-outline bg-subtle p-5">
        <h3 className="text-sm font-semibold text-ink">Generated paper track record</h3>
        <p className="mt-1 text-xs text-muted">Paper performance is loading or unavailable.</p>
      </section>
    );
  }
  const progress = Math.min(
    (data.settled_tickets / Math.max(data.tracking_target, 1)) * 100,
    100,
  );
  const signedUnits = `${data.unit_profit > 0 ? "+" : ""}${data.unit_profit.toFixed(2)}u`;
  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold text-ink">Generated paper track record</h3>
          <p className="mt-1 text-xs text-muted">
            Daily tickets only, normalized to one simulated unit each.
          </p>
        </div>
        <span className="rounded-full border border-warn-line bg-warn-faint px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-warn-strong">
          {data.settled_tickets} / {data.tracking_target} tracked
        </span>
      </div>
      <div className="grid grid-cols-2 gap-px bg-hairline md:grid-cols-4">
        <div className="bg-surface px-5 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">Settled</p>
          <p className="mt-1 text-xl font-bold tabular-nums text-ink">{number(data.settled_tickets)}</p>
          <p className="text-[11px] text-faint">{number(data.pending_tickets)} pending</p>
        </div>
        <div className="bg-surface px-5 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">Record</p>
          <p className="mt-1 text-xl font-bold tabular-nums text-ink">
            {data.won_tickets}–{data.lost_tickets}
          </p>
          <p className="text-[11px] text-faint">{percent(data.win_rate)} hit rate</p>
        </div>
        <div className="bg-surface px-5 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">Unit P&amp;L</p>
          <p className={`mt-1 text-xl font-bold tabular-nums ${data.unit_profit > 0 ? "text-success" : data.unit_profit < 0 ? "text-danger" : "text-ink"}`}>
            {signedUnits}
          </p>
          <p className="text-[11px] text-faint">{data.unit_staked.toFixed(0)}u staked</p>
        </div>
        <div className="bg-surface px-5 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">Unit ROI</p>
          <p className={`mt-1 text-xl font-bold tabular-nums ${data.unit_roi !== null && data.unit_roi > 0 ? "text-success" : data.unit_roi !== null && data.unit_roi < 0 ? "text-danger" : "text-ink"}`}>
            {percent(data.unit_roi, true)}
          </p>
          <p className="text-[11px] text-faint">avg odds {data.average_odds?.toFixed(2) ?? "—"}</p>
        </div>
      </div>
      <div className="px-5 py-4">
        <div className="h-1.5 overflow-hidden rounded-full bg-hairline">
          <div className="h-full rounded-full bg-accent" style={{ width: `${progress}%` }} />
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-muted">{data.note}</p>
      </div>
    </section>
  );
}

function Coverage({ data }: { data: ModelReadinessView }) {
  return (
    <section className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
      <div className="mb-5">
        <h3 className="text-sm font-semibold text-ink">Dataset coverage</h3>
        <p className="mt-1 text-xs text-faint">
          A zero means the market cannot be honestly ROI-tested yet.
        </p>
      </div>
      <div className="grid gap-x-8 gap-y-4 md:grid-cols-2">
        {data.coverage.map((item) => (
          <div key={item.key}>
            <div className="mb-1.5 flex items-center justify-between gap-3">
              <span className="text-xs font-medium text-ink-soft">{item.label}</span>
              <span className="text-[11px] tabular-nums text-muted">
                {number(item.records)} · {item.percent.toFixed(1)}%
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-hairline">
              <div
                className={`h-full rounded-full ${
                  item.percent >= 90
                    ? "bg-success-bright"
                    : item.percent > 0
                      ? "bg-accent"
                      : "bg-outline"
                }`}
                style={{ width: `${Math.max(item.percent, item.percent > 0 ? 2 : 0)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function MarketCard({ market }: { market: MarketReadinessView }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-ink">{market.label}</h4>
        <StageBadge stage={market.stage} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 min-[420px]:grid-cols-3">
        <div className="rounded-lg bg-subtle p-2.5">
          <p className="text-[9px] font-semibold uppercase tracking-widest text-faint">
            Training rows
          </p>
          <p className="mt-1 text-sm font-bold tabular-nums text-ink">
            {number(market.training_rows)}
          </p>
        </div>
        <div className="rounded-lg bg-subtle p-2.5">
          <p className="text-[9px] font-semibold uppercase tracking-widest text-faint">
            Settled
          </p>
          <p className="mt-1 text-sm font-bold tabular-nums text-ink">
            {number(market.settled_rows)}
          </p>
        </div>
        <div className="rounded-lg bg-subtle p-2.5">
          <p className="text-[9px] font-semibold uppercase tracking-widest text-faint">
            Odds rows
          </p>
          <p className="mt-1 text-sm font-bold tabular-nums text-ink">
            {number(market.odds_rows)}
          </p>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-[11px]">
        {market.roi_validated ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-success" />
        ) : (
          <ShieldAlert className="h-3.5 w-3.5 text-warn" />
        )}
        <span className={market.roi_validated ? "text-success-deep" : "text-warn-strong"}>
          {market.roi_validated ? "ROI validated" : "ROI not validated"}
        </span>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-muted">{market.note}</p>
    </div>
  );
}

function Validation({ report }: { report?: EvaluationReportView }) {
  if (!report) {
    return (
      <section className="rounded-2xl border border-dashed border-outline bg-subtle p-5">
        <h3 className="text-sm font-semibold text-ink">Latest validation</h3>
        <p className="mt-1 text-xs text-muted">
          No evaluation has been published yet. Model claims remain unvalidated.
        </p>
      </section>
    );
  }

  const { model, market, strategy } = report.overall;
  const beatsMarket = model.log_loss < market.log_loss && model.brier < market.brier;
  const metrics = [
    { label: "Accuracy", model: percent(model.accuracy), market: percent(market.accuracy) },
    { label: "Log loss ↓", model: model.log_loss.toFixed(4), market: market.log_loss.toFixed(4) },
    { label: "Brier ↓", model: model.brier.toFixed(4), market: market.brier.toFixed(4) },
    {
      label: "Calibration error ↓",
      model: percent(model.calibration_error),
      market: percent(market.calibration_error),
    },
  ];

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
      <div className="flex flex-col justify-between gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-center">
        <div>
          <h3 className="text-sm font-semibold text-ink">Latest unseen-season validation</h3>
          <p className="mt-1 text-xs text-faint">
            {number(model.matches)} matches · {report.leagues.reduce((n, item) => n + item.folds.length, 0)} folds · published {date(report.generated_at)}
          </p>
        </div>
        <span
          className={`self-start rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-widest sm:self-center ${
            beatsMarket
              ? "border-success-line bg-success-faint text-success-deep"
              : "border-danger-line bg-danger-faint text-danger-deep"
          }`}
        >
          {beatsMarket ? "Beats market baseline" : "Below market baseline"}
        </span>
      </div>

      <div className="grid xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.3fr)]">
        <div className="border-b border-border p-5 xl:border-r xl:border-b-0">
          <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-x-5 gap-y-3 text-xs">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">Metric</p>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">Model</p>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">Market</p>
            {metrics.map((metric) => (
              <div key={metric.label} className="contents">
                <p className="text-muted">{metric.label}</p>
                <p className="text-right font-semibold tabular-nums text-ink">{metric.model}</p>
                <p className="text-right font-semibold tabular-nums text-ink">{metric.market}</p>
              </div>
            ))}
          </div>

          <div className="mt-5 rounded-xl border border-warn-line bg-warn-faint p-3.5">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-warn" />
              <p className="text-xs font-semibold text-warn-strong">Value strategy result</p>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 min-[420px]:grid-cols-3">
              <div>
                <p className="text-[9px] uppercase tracking-widest text-warn-mid">Bets</p>
                <p className="mt-1 text-sm font-bold tabular-nums text-warn-deep">{number(strategy.bets)}</p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-widest text-warn-mid">ROI</p>
                <p className="mt-1 text-sm font-bold tabular-nums text-warn-deep">{percent(strategy.roi, true)}</p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-widest text-warn-mid">95% interval</p>
                <p className="mt-1 text-[11px] font-bold tabular-nums text-warn-deep">
                  {percent(strategy.roi_ci_low)} to {percent(strategy.roi_ci_high)}
                </p>
              </div>
            </div>
          </div>
        </div>

        <ScrollArea label="League validation table">
          <table className="w-full min-w-[580px] text-left text-xs">
            <thead className="bg-subtle text-[10px] uppercase tracking-widest text-faint">
              <tr>
                <th className="px-5 py-2.5 font-semibold">League</th>
                <th className="px-4 py-2.5 font-semibold">Model log loss</th>
                <th className="px-4 py-2.5 font-semibold">Market</th>
                <th className="px-4 py-2.5 font-semibold">ROI</th>
                <th className="px-5 py-2.5 font-semibold">95% interval</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {report.leagues.map((league) => (
                <tr key={league.league}>
                  <td className="px-5 py-3 font-medium text-ink">{league.league}</td>
                  <td className="px-4 py-3 tabular-nums text-ink-soft">{league.summary.model.log_loss.toFixed(4)}</td>
                  <td className="px-4 py-3 tabular-nums text-ink-soft">{league.summary.market.log_loss.toFixed(4)}</td>
                  <td className="px-4 py-3 tabular-nums text-ink-soft">{percent(league.summary.strategy.roi, true)}</td>
                  <td className="px-5 py-3 tabular-nums text-muted">
                    {percent(league.summary.strategy.roi_ci_low)} to {percent(league.summary.strategy.roi_ci_high)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollArea>
      </div>
    </section>
  );
}

function CornerValidation({
  report,
  priceFixtures,
}: {
  report?: CornerEvaluationReportView;
  priceFixtures: number;
}) {
  if (!report) return null;
  const { model, baseline } = report.overall;
  const improvementIsReliable =
    report.overall.improvement_ci_low !== null && report.overall.improvement_ci_low > 0;

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
      <div className="flex flex-col justify-between gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-center">
        <div>
          <h3 className="text-sm font-semibold text-ink">Corner-count validation</h3>
          <p className="mt-1 text-xs text-faint">
            {number(model.matches)} unseen matches · {report.model_name}
          </p>
        </div>
        <span className="self-start rounded-full border border-warn-line bg-warn-faint px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-warn-strong sm:self-center">
          ROI unavailable · {number(priceFixtures)} priced fixtures
        </span>
      </div>

      <div className="grid xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.4fr)]">
        <div className="border-b border-border p-5 xl:border-r xl:border-b-0">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-subtle p-3">
              <p className="text-[9px] font-semibold uppercase tracking-widest text-faint">Model MAE ↓</p>
              <p className="mt-1 text-lg font-bold tabular-nums text-ink">{model.mae.toFixed(4)}</p>
            </div>
            <div className="rounded-xl bg-subtle p-3">
              <p className="text-[9px] font-semibold uppercase tracking-widest text-faint">Baseline MAE</p>
              <p className="mt-1 text-lg font-bold tabular-nums text-ink">{baseline.mae.toFixed(4)}</p>
            </div>
          </div>
          <p className={`mt-3 text-xs font-medium ${improvementIsReliable ? "text-success-deep" : "text-warn-strong"}`}>
            Paired MAE gain {report.overall.mae_improvement.toFixed(4)} · 95% interval {report.overall.improvement_ci_low?.toFixed(4) ?? "—"} to {report.overall.improvement_ci_high?.toFixed(4) ?? "—"}
          </p>
          <p className="mt-3 text-[11px] leading-relaxed text-muted">
            {priceFixtures > 0
              ? `${number(priceFixtures)} fixtures now have captured corner prices. ROI remains unavailable until those fixtures settle and the sample becomes meaningful.`
              : report.limitation}
          </p>
        </div>

        <ScrollArea label="Corner model validation table">
          <table className="w-full min-w-[560px] text-left text-xs">
            <thead className="bg-subtle text-[10px] uppercase tracking-widest text-faint">
              <tr>
                <th className="px-5 py-2.5 font-semibold">League</th>
                <th className="px-4 py-2.5 font-semibold">Model MAE</th>
                <th className="px-4 py-2.5 font-semibold">Baseline</th>
                <th className="px-4 py-2.5 font-semibold">Gain</th>
                <th className="px-5 py-2.5 font-semibold">95% interval</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {report.leagues.map((league) => (
                <tr key={league.league}>
                  <td className="px-5 py-3 font-medium text-ink">{league.league}</td>
                  <td className="px-4 py-3 tabular-nums text-ink-soft">{league.summary.model.mae.toFixed(4)}</td>
                  <td className="px-4 py-3 tabular-nums text-ink-soft">{league.summary.baseline.mae.toFixed(4)}</td>
                  <td className="px-4 py-3 tabular-nums text-ink-soft">{league.summary.mae_improvement.toFixed(4)}</td>
                  <td className="px-5 py-3 tabular-nums text-muted">
                    {league.summary.improvement_ci_low?.toFixed(4) ?? "—"} to {league.summary.improvement_ci_high?.toFixed(4) ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollArea>
      </div>
    </section>
  );
}

function ModelLabContent({
  data,
  evaluation,
  cornerEvaluation,
  paperPerformance,
}: {
  data: ModelReadinessView;
  evaluation?: EvaluationReportView;
  cornerEvaluation?: CornerEvaluationReportView;
  paperPerformance?: PaperPerformanceView;
}) {
  const stale = data.freshness_days !== null && data.freshness_days > 45;
  const cornerPriceFixtures =
    data.markets.find((market) => market.key === "corners")?.odds_rows ?? 0;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col justify-between gap-3 rounded-2xl border border-accent-line bg-gradient-to-br from-white to-accent-faint p-5 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <BrainCircuit className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold text-ink">{data.model_name}</h2>
          </div>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted">
            Live as an explainable research baseline. It is allowed to generate probabilities,
            but no market is labelled profitable until walk-forward ROI is validated.
          </p>
        </div>
        <span className="self-start rounded-full border border-info-line bg-surface px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-info sm:self-center">
          Research baseline
        </span>
      </div>

      {stale && (
        <div className="flex items-start gap-2 rounded-xl border border-warn-line bg-warn-faint px-4 py-3 text-xs text-warn-deep">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <p>
            Latest historical result is {data.freshness_days} days old. Add current-season
            results and pre-match snapshots before treating today&apos;s recommendations as fresh.
          </p>
        </div>
      )}

      <Summary data={data} />
      <PaperPerformance data={paperPerformance} />
      <Validation report={evaluation} />
      <CornerValidation report={cornerEvaluation} priceFixtures={cornerPriceFixtures} />
      <Coverage data={data} />

      <section>
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-ink">Market readiness</h3>
          <p className="mt-1 text-xs text-faint">Prediction coverage is not proof of profit.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {data.markets.map((market) => (
            <MarketCard key={market.key} market={market} />
          ))}
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <section className="overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
          <div className="border-b border-border px-5 py-4">
            <h3 className="text-sm font-semibold text-ink">League depth</h3>
          </div>
          <ScrollArea label="League data depth table">
            <table className="w-full min-w-[520px] text-left text-xs">
              <thead className="bg-subtle text-[10px] uppercase tracking-widest text-faint">
                <tr>
                  <th className="px-5 py-2.5 font-semibold">League</th>
                  <th className="px-5 py-2.5 font-semibold">Matches</th>
                  <th className="px-5 py-2.5 font-semibold">From</th>
                  <th className="px-5 py-2.5 font-semibold">Through</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {data.league_coverage.map((league) => (
                  <tr key={league.league}>
                    <td className="px-5 py-3 font-medium text-ink">{league.league}</td>
                    <td className="px-5 py-3 tabular-nums text-ink-soft">
                      {number(league.matches)}
                    </td>
                    <td className="px-5 py-3 text-muted">{date(league.date_from)}</td>
                    <td className="px-5 py-3 text-muted">{date(league.date_to)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollArea>
        </section>

        <section className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-ink">What moves us forward</h3>
          <ol className="mt-4 flex flex-col gap-3">
            {data.next_priorities.map((priority, index) => (
              <li key={priority} className="flex gap-3 text-xs leading-relaxed text-muted-strong">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-light text-[10px] font-bold text-accent">
                  {index + 1}
                </span>
                {priority}
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
}

export function ModelLab() {
  const query = useQuery({
    queryKey: ["model-readiness"],
    queryFn: fetchModelReadiness,
    staleTime: 5 * 60_000,
  });
  const evaluationQuery = useQuery({
    queryKey: ["model-evaluation-latest"],
    queryFn: fetchLatestEvaluation,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const cornerEvaluationQuery = useQuery({
    queryKey: ["corner-evaluation-latest"],
    queryFn: fetchLatestCornerEvaluation,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const paperPerformanceQuery = useQuery({
    queryKey: ["paper-performance"],
    queryFn: fetchPaperPerformance,
    staleTime: 60_000,
    retry: false,
  });

  if (query.isLoading) {
    return (
      <div className="flex min-h-64 items-center justify-center rounded-2xl border border-border bg-surface">
        <Spinner />
      </div>
    );
  }
  if (query.isError || !query.data) {
    return (
      <div className="rounded-xl border border-danger-soft bg-danger-faint px-4 py-4 text-sm text-danger">
        Could not load model readiness. Check that the API is running and the new database
        schema has been deployed.
      </div>
    );
  }
  return (
    <ModelLabContent
      data={query.data}
      evaluation={evaluationQuery.data}
      cornerEvaluation={cornerEvaluationQuery.data}
      paperPerformance={paperPerformanceQuery.data}
    />
  );
}
