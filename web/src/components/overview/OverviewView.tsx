"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  ChevronRight,
  FlaskConical,
  ListChecks,
  Target,
  Wallet,
} from "lucide-react";
import { fetchCalendar, fetchPaperPerformance, fetchPipelineHealth, fetchSlips } from "@/lib/api";
import type { CalendarDay, DailyAccaView, SlipView } from "@/lib/types";
import {
  addDays,
  dateFromISO,
  formatKickoffShort,
  formatOdds,
  formatPercent,
  formatSignedCurrency,
  hasFinished,
  legLabel,
  toLocalISODate,
  todayISO,
} from "@/lib/utils";
import { PnlChart } from "@/components/charts/PnlChart";
import { dailyAccaQuery } from "@/components/generator/DailyAcca";
import { SlipCard } from "@/components/slips/SlipCard";
import { Skeleton } from "@/components/ui/Spinner";

/** Pending slips whose last kickoff has passed — these are waiting on you. */
function needsSettling(slips: SlipView[]): SlipView[] {
  const now = Date.now();
  return slips.filter((slip) => {
    if (slip.result !== "pending" || slip.legs.length === 0) return false;
    return slip.legs.every((l) => hasFinished(l.kickoff_utc, now));
  });
}

type Tone = "accent" | "success" | "warn" | "info";

const TILE_TONE: Record<Tone, string> = {
  accent: "bg-accent-light text-accent border-accent-line",
  success: "bg-success-faint text-success border-success-line",
  warn: "bg-warn-soft text-warn border-warn-line",
  info: "bg-info-faint text-info border-info-line",
};

function KpiTile({
  label,
  value,
  detail,
  icon: Icon,
  tone,
  valueClass = "text-ink",
  loading,
}: {
  label: string;
  value: string;
  detail: string;
  icon: React.ElementType;
  tone: Tone;
  valueClass?: string;
  loading: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-2xl border border-border bg-surface p-5 shadow-card">
      <span className={`flex h-10 w-10 items-center justify-center rounded-xl border ${TILE_TONE[tone]}`}>
        <Icon size={18} />
      </span>
      <div className="min-w-0">
        {loading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <p className={`truncate text-2xl font-semibold tracking-tight ${valueClass}`}>{value}</p>
        )}
        <p className="mt-1 text-xs font-medium text-muted">{label}</p>
        <p className="mt-0.5 truncate text-[11px] text-faint">{detail}</p>
      </div>
    </div>
  );
}

function signedClass(value: number): string {
  return value > 0 ? "text-success" : value < 0 ? "text-danger" : "text-ink";
}

function CardHeader({ title, href, linkLabel }: { title: string; href?: string; linkLabel?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      {href && (
        <Link
          href={href}
          className="flex min-h-[40px] items-center gap-1 rounded-lg px-2 text-sm text-muted transition-colors hover:text-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[32px]"
        >
          {linkLabel}
          <ChevronRight size={15} />
        </Link>
      )}
    </div>
  );
}

function TodaySlip({ data, loading }: { data: DailyAccaView | undefined; loading: boolean }) {
  if (loading) {
    return (
      <div className="mt-4 flex flex-col gap-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }
  if (!data || data.legs.length === 0) {
    return (
      <p className="mt-4 rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
        No slip today.{" "}
        {data ? `${data.fixtures_scanned} fixtures scanned, nothing cleared the filters.` : ""}
      </p>
    );
  }
  return (
    <div className="mt-4 flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-2xl font-semibold tracking-tight text-ink">{formatOdds(data.combined_odds)}</p>
        <p className="text-sm text-muted">
          lands <span className="font-semibold text-ink">{formatPercent(data.combined_model_prob)}</span>
        </p>
      </div>
      <ul className="flex flex-col divide-y divide-hairline rounded-xl border border-border">
        {data.legs.map((leg) => (
          <li key={`${leg.fixture_id}-${leg.selection}`} className="flex items-center gap-3 px-3 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-ink">
                {legLabel(leg.market_type, leg.selection, leg.point, leg.home_team, leg.away_team)}
              </p>
              <p className="truncate text-[11px] text-faint">
                {leg.home_team} vs {leg.away_team}
                {leg.kickoff_utc ? ` · ${formatKickoffShort(leg.kickoff_utc)}` : ""}
              </p>
            </div>
            <span className="shrink-0 text-sm font-semibold tabular-nums text-ink">
              {formatOdds(leg.offered_odds)}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-faint">
        {data.execution_mode === "paper" ? "Paper only — tracked, not staked." : data.staking.note}
      </p>
    </div>
  );
}

function UpcomingStrip({ days }: { days: CalendarDay[] }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {days.map((day) => {
        const d = dateFromISO(day.date);
        const playable = day.model?.target_met;
        return (
          <Link
            key={day.date}
            href={`/matches/calendar/${day.date}`}
            className="flex min-w-0 flex-col gap-1 rounded-xl border border-border bg-surface px-3 py-2.5 transition-colors hover:border-accent/40 hover:bg-accent-light/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          >
            <span className="text-xs font-medium text-muted">
              {d.toLocaleDateString(undefined, { weekday: "short", day: "numeric" })}
            </span>
            <span className="text-sm font-semibold tabular-nums text-ink">
              {day.fixture_count}
              <span className="ml-1 text-[11px] font-normal text-faint">
                {day.fixture_count === 1 ? "match" : "matches"}
              </span>
            </span>
            <span className={`truncate text-[11px] font-medium ${playable ? "text-success" : "text-faint"}`}>
              {playable
                ? `${Math.round((day.model?.combined_model_prob ?? 0) * 100)}% @ ${day.model?.combined_odds.toFixed(2)}`
                : day.fixture_count === 0
                  ? "No card"
                  : day.priced_fixture_count === 0
                    ? "Odds pending"
                    : "No target slip"}
            </span>
          </Link>
        );
      })}
    </div>
  );
}

/**
 * The scheduled jobs fail out of sight. Without this, a dead API key only shows
 * up weeks later as "the model stopped making tickets".
 */
function PipelineWarning({ problems, lastCapture }: { problems: string[]; lastCapture: string | null }) {
  return (
    <section
      role="status"
      className="flex gap-3 rounded-xl border border-warn/25 bg-warn-soft/60 px-4 py-3"
    >
      <AlertCircle size={16} className="mt-0.5 shrink-0 text-warn" />
      <div className="min-w-0 flex-1 text-sm text-warn-strong">
        <p className="font-semibold">The paper track is not being fed.</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
        <p className="mt-1 text-xs">
          Last odds capture: {lastCapture ? formatKickoffShort(lastCapture) : "never"}
        </p>
      </div>
    </section>
  );
}

export function OverviewView() {
  const today = todayISO();
  const weekEnd = toLocalISODate(addDays(dateFromISO(today), 6));
  const queryClient = useQueryClient();

  const slipsQuery = useQuery({ queryKey: ["slips"], queryFn: fetchSlips });
  const paperQuery = useQuery({ queryKey: ["paper-performance"], queryFn: fetchPaperPerformance });
  const healthQuery = useQuery({ queryKey: ["pipeline-health"], queryFn: fetchPipelineHealth });
  const weekQuery = useQuery({
    queryKey: ["calendar", today, weekEnd],
    queryFn: () => fetchCalendar(today, weekEnd),
  });
  // Opening the home page archives today's 1.50 paper ticket, as Today used to.
  const dailyQuery = useQuery(dailyAccaQuery({ date: today, autoTrack: true }));

  useEffect(() => {
    if (!dailyQuery.data?.auto_tracked) return;
    queryClient.invalidateQueries({ queryKey: ["slips"] });
    queryClient.invalidateQueries({ queryKey: ["paper-performance"] });
  }, [dailyQuery.data?.auto_tracked, queryClient]);

  const slips = useMemo(() => slipsQuery.data ?? [], [slipsQuery.data]);
  const toSettle = useMemo(() => needsSettling(slips), [slips]);
  const currency = slips[0]?.currency ?? "ZAR";
  const settled = slips.filter((s) => s.result !== "pending");
  const won = settled.filter((s) => s.result === "won").length;
  const pending = slips.filter((s) => s.result === "pending");
  const pnl = settled.reduce((acc, s) => acc + s.profit_loss, 0);
  const atRisk = pending.reduce((acc, s) => acc + s.stake, 0);
  const paper = paperQuery.data;

  const todayCard = weekQuery.data?.days.find((d) => d.date === today);
  const upcoming = weekQuery.data?.days.filter((d) => d.date > today) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">Overview</h1>
        <p className="mt-1 text-sm text-muted">
          {todayCard
            ? `${todayCard.fixture_count} ${todayCard.fixture_count === 1 ? "match" : "matches"} today across ${todayCard.leagues.length} ${todayCard.leagues.length === 1 ? "league" : "leagues"}.`
            : "Your betting at a glance."}
        </p>
      </div>

      {healthQuery.data && !healthQuery.data.healthy && (
        <PipelineWarning problems={healthQuery.data.problems} lastCapture={healthQuery.data.last_odds_capture_at} />
      )}

      <div className="grid grid-cols-1 gap-4 min-[420px]:grid-cols-2 xl:grid-cols-4">
        <KpiTile
          label="Net profit / loss"
          value={settled.length ? formatSignedCurrency(pnl, currency) : "—"}
          detail={`${settled.length} settled ${settled.length === 1 ? "slip" : "slips"}`}
          icon={Wallet}
          tone="accent"
          valueClass={signedClass(pnl)}
          loading={slipsQuery.isLoading}
        />
        <KpiTile
          label="Hit rate"
          value={settled.length ? formatPercent(won / settled.length) : "—"}
          detail={`${won} won · ${settled.length - won} lost`}
          icon={Target}
          tone="success"
          loading={slipsQuery.isLoading}
        />
        <KpiTile
          label="Open slips"
          value={String(pending.length)}
          detail={pending.length ? `${currency} ${atRisk.toFixed(2)} at risk` : "Nothing at risk"}
          icon={ListChecks}
          tone="warn"
          loading={slipsQuery.isLoading}
        />
        <KpiTile
          label="Paper ROI"
          value={paper?.unit_roi == null ? "—" : `${paper.unit_roi > 0 ? "+" : ""}${formatPercent(paper.unit_roi, 1)}`}
          detail={paper ? `${paper.settled_tickets} of ${paper.tracking_target} tickets tracked` : "Model track record"}
          icon={FlaskConical}
          tone="info"
          valueClass={paper?.unit_roi == null ? "text-ink" : signedClass(paper.unit_roi)}
          loading={paperQuery.isLoading}
        />
      </div>

      {toSettle.length > 0 && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-warn/25 bg-warn-soft/60 px-4 py-3">
            <AlertCircle size={16} className="shrink-0 text-warn" />
            <p className="min-w-0 flex-1 text-sm text-warn-strong">
              <span className="font-semibold">
                {toSettle.length} {toSettle.length === 1 ? "slip has" : "slips have"} finished
              </span>{" "}
              and {toSettle.length === 1 ? "is" : "are"} waiting to be settled.
            </p>
            <Link
              href="/slips"
              className="flex min-h-[40px] shrink-0 items-center gap-1 rounded-lg px-2.5 text-sm font-medium text-warn transition-colors hover:bg-warn-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-warn/40 sm:min-h-[32px]"
            >
              Settle
              <ArrowRight size={14} />
            </Link>
          </div>
          <div className="grid items-start gap-3 xl:grid-cols-2">
            {toSettle.slice(0, 2).map((slip) => (
              <SlipCard key={slip.id} slip={slip} />
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="rounded-2xl border border-border bg-surface p-5 shadow-card lg:col-span-2">
          <CardHeader title="Profit over time" href="/analytics" linkLabel="Analytics" />
          <p className="mb-4 mt-1 text-xs text-muted">Running total after each settled slip.</p>
          <PnlChart slips={slips} currency={currency} />
        </section>

        <section className="rounded-2xl border border-border bg-surface p-5 shadow-card">
          <CardHeader title="Today's slip" href="/picks" linkLabel="Picks" />
          <TodaySlip data={dailyQuery.data} loading={dailyQuery.isLoading} />
        </section>
      </div>

      {upcoming.length > 0 && (
        <section className="flex flex-col gap-3">
          <CardHeader title="Next 6 days" href="/matches/calendar" linkLabel="Calendar" />
          <UpcomingStrip days={upcoming} />
        </section>
      )}
    </div>
  );
}
