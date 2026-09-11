"use client";

import { useQuery } from "@tanstack/react-query";
import { Pin, Trophy } from "lucide-react";
import { fetchPersonalPool } from "@/lib/api";
import { formatOdds } from "@/lib/utils";
import { EmptyState } from "@/components/ui/EmptyState";
import { SpinnerOverlay } from "@/components/ui/Spinner";

export function PersonalPool() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["personal-pool"],
    queryFn: fetchPersonalPool,
  });
  if (isLoading) return <SpinnerOverlay label="Loading personal pool…" />;
  if (isError) return <p className="rounded-xl border border-danger-line bg-danger-faint px-4 py-3 text-sm text-danger">{error instanceof Error ? error.message : "Could not load your pool."}</p>;
  if (!data) return null;

  return <div className="flex flex-col gap-5">
    <p className="rounded-xl border border-accent/25 bg-accent-light/50 px-4 py-3 text-sm leading-relaxed text-muted">{data.note}</p>
    <div className="grid gap-3 sm:grid-cols-2">
      {data.summaries.map((summary) => <div key={summary.pool} className="rounded-xl border border-border bg-surface p-4 shadow-card">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">{summary.label}</p>
        <div className="mt-2 flex items-end justify-between gap-3"><p className="text-2xl font-semibold tabular-nums text-ink">{summary.total}</p><p className="text-sm font-semibold text-accent">{summary.win_rate === null ? "No settled picks" : `${Math.round(summary.win_rate * 100)}% won`}</p></div>
        <p className="mt-1 text-xs text-muted">{summary.pending} pending · {summary.won} won · {summary.lost} lost{summary.void ? ` · ${summary.void} void` : ""}</p>
      </div>)}
    </div>
    {data.entries.length === 0 ? <EmptyState icon={<Pin size={22} />} title="Your pool is empty" description="In Build, pin a Home/Away winner or a corner-total selection to make it a personal favourite." /> :
      <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
        {data.entries.map((entry) => <div key={entry.id} className="flex items-center gap-3 border-b border-hairline px-4 py-3 last:border-0">
          <Trophy size={15} className="shrink-0 text-accent" />
          <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-ink">{entry.home_team} <span className="text-faint">vs</span> {entry.away_team}</p><p className="mt-0.5 text-xs text-muted">{entry.pool === "straight_win" ? "Straight win" : "Corners"} · {entry.selection}{entry.point !== null ? ` ${entry.point}` : ""}</p></div>
          <div className="text-right"><p className="text-sm font-semibold tabular-nums text-ink">{formatOdds(entry.price)}</p><p className={`mt-0.5 text-[10px] font-semibold uppercase tracking-wider ${entry.result === "won" ? "text-success" : entry.result === "lost" ? "text-danger" : "text-faint"}`}>{entry.result}</p></div>
        </div>)}
      </div>}
  </div>;
}
