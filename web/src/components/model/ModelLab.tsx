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
import { fetchModelReadiness } from "@/lib/api";
import type { MarketReadinessView, ModelReadinessView } from "@/lib/types";
import { Spinner } from "@/components/ui/Spinner";

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

function StageBadge({ stage }: { stage: MarketReadinessView["stage"] }) {
  const styles = {
    baseline: "border-[#C7D2FE] bg-[#EEF2FF] text-[#4338CA]",
    research: "border-[#FDE68A] bg-[#FFFBEB] text-[#92400E]",
    blocked: "border-[#E5E7EB] bg-[#F9FAFB] text-[#6B7280]",
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
    {
      label: "Latest result",
      value: date(data.date_to),
      icon: CircleDashed,
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {items.map(({ label, value, icon: Icon }) => (
        <div key={label} className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 text-[#9CA3AF]">
            <Icon className="h-3.5 w-3.5" />
            <p className="text-[10px] font-semibold uppercase tracking-widest">{label}</p>
          </div>
          <p className="mt-2 text-xl font-bold tracking-tight text-[#111827]">{value}</p>
        </div>
      ))}
    </div>
  );
}

function Coverage({ data }: { data: ModelReadinessView }) {
  return (
    <section className="rounded-2xl border border-[#E5E7EB] bg-white p-5 shadow-sm">
      <div className="mb-5">
        <h3 className="text-sm font-semibold text-[#111827]">Dataset coverage</h3>
        <p className="mt-1 text-xs text-[#9CA3AF]">
          A zero means the market cannot be honestly ROI-tested yet.
        </p>
      </div>
      <div className="grid gap-x-8 gap-y-4 md:grid-cols-2">
        {data.coverage.map((item) => (
          <div key={item.key}>
            <div className="mb-1.5 flex items-center justify-between gap-3">
              <span className="text-xs font-medium text-[#374151]">{item.label}</span>
              <span className="text-[11px] tabular-nums text-[#6B7280]">
                {number(item.records)} · {item.percent.toFixed(1)}%
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-[#F3F4F6]">
              <div
                className={`h-full rounded-full ${
                  item.percent >= 90
                    ? "bg-[#10B981]"
                    : item.percent > 0
                      ? "bg-[#6C47FF]"
                      : "bg-[#D1D5DB]"
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
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-[#111827]">{market.label}</h4>
        <StageBadge stage={market.stage} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <div className="rounded-lg bg-[#F9FAFB] p-2.5">
          <p className="text-[9px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
            Training rows
          </p>
          <p className="mt-1 text-sm font-bold tabular-nums text-[#111827]">
            {number(market.training_rows)}
          </p>
        </div>
        <div className="rounded-lg bg-[#F9FAFB] p-2.5">
          <p className="text-[9px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
            Odds rows
          </p>
          <p className="mt-1 text-sm font-bold tabular-nums text-[#111827]">
            {number(market.odds_rows)}
          </p>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-[11px]">
        {market.roi_validated ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-[#059669]" />
        ) : (
          <ShieldAlert className="h-3.5 w-3.5 text-[#D97706]" />
        )}
        <span className={market.roi_validated ? "text-[#047857]" : "text-[#92400E]"}>
          {market.roi_validated ? "ROI validated" : "ROI not validated"}
        </span>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-[#6B7280]">{market.note}</p>
    </div>
  );
}

function ModelLabContent({ data }: { data: ModelReadinessView }) {
  const stale = data.freshness_days !== null && data.freshness_days > 45;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col justify-between gap-3 rounded-2xl border border-[#DDD6FE] bg-gradient-to-br from-white to-[#F5F3FF] p-5 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <BrainCircuit className="h-4 w-4 text-[#6C47FF]" />
            <h2 className="text-sm font-semibold text-[#111827]">{data.model_name}</h2>
          </div>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[#6B7280]">
            Live as an explainable research baseline. It is allowed to generate probabilities,
            but no market is labelled profitable until walk-forward ROI is validated.
          </p>
        </div>
        <span className="self-start rounded-full border border-[#C7D2FE] bg-white px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-[#4338CA] sm:self-center">
          Research baseline
        </span>
      </div>

      {stale && (
        <div className="flex items-start gap-2 rounded-xl border border-[#FDE68A] bg-[#FFFBEB] px-4 py-3 text-xs text-[#78350F]">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#D97706]" />
          <p>
            Latest historical result is {data.freshness_days} days old. Add current-season
            results and pre-match snapshots before treating today&apos;s recommendations as fresh.
          </p>
        </div>
      )}

      <Summary data={data} />
      <Coverage data={data} />

      <section>
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-[#111827]">Market readiness</h3>
          <p className="mt-1 text-xs text-[#9CA3AF]">Prediction coverage is not proof of profit.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {data.markets.map((market) => (
            <MarketCard key={market.key} market={market} />
          ))}
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <section className="overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-sm">
          <div className="border-b border-[#E5E7EB] px-5 py-4">
            <h3 className="text-sm font-semibold text-[#111827]">League depth</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-xs">
              <thead className="bg-[#F9FAFB] text-[10px] uppercase tracking-widest text-[#9CA3AF]">
                <tr>
                  <th className="px-5 py-2.5 font-semibold">League</th>
                  <th className="px-5 py-2.5 font-semibold">Matches</th>
                  <th className="px-5 py-2.5 font-semibold">From</th>
                  <th className="px-5 py-2.5 font-semibold">Through</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#F3F4F6]">
                {data.league_coverage.map((league) => (
                  <tr key={league.league}>
                    <td className="px-5 py-3 font-medium text-[#111827]">{league.league}</td>
                    <td className="px-5 py-3 tabular-nums text-[#374151]">
                      {number(league.matches)}
                    </td>
                    <td className="px-5 py-3 text-[#6B7280]">{date(league.date_from)}</td>
                    <td className="px-5 py-3 text-[#6B7280]">{date(league.date_to)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-2xl border border-[#E5E7EB] bg-white p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-[#111827]">What moves us forward</h3>
          <ol className="mt-4 flex flex-col gap-3">
            {data.next_priorities.map((priority, index) => (
              <li key={priority} className="flex gap-3 text-xs leading-relaxed text-[#4B5563]">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#EEE9FF] text-[10px] font-bold text-[#6C47FF]">
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

  if (query.isLoading) {
    return (
      <div className="flex min-h-64 items-center justify-center rounded-2xl border border-[#E5E7EB] bg-white">
        <Spinner />
      </div>
    );
  }
  if (query.isError || !query.data) {
    return (
      <div className="rounded-xl border border-[#FEE2E2] bg-[#FEF2F2] px-4 py-4 text-sm text-[#DC2626]">
        Could not load model readiness. Check that the API is running and the new database
        schema has been deployed.
      </div>
    );
  }
  return <ModelLabContent data={query.data} />;
}
