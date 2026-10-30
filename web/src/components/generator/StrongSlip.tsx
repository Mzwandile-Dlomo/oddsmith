"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check, CheckCircle, Flame, Minus, Plus } from "lucide-react";
import { createSlip, fetchStrongAcca } from "@/lib/api";
import type { StrongLegView, StrongSlipView } from "@/lib/types";
import { ShareSlip } from "@/components/picks/ShareSlip";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Spinner } from "@/components/ui/Spinner";
import {
  addDays,
  combinedOdds,
  dateFromISO,
  formatKickoff,
  formatOdds,
  formatPercent,
  toLocalISODate,
  todayISO,
} from "@/lib/utils";

type WindowKey = "next2" | "weekend" | "next3";

/** Local `YYYY-MM-DD` bounds for a window preset, inclusive. */
function windowRange(key: WindowKey): { from: string; to: string } {
  const today = dateFromISO(todayISO());
  if (key === "next2") return { from: toLocalISODate(today), to: toLocalISODate(addDays(today, 1)) };
  if (key === "next3") return { from: toLocalISODate(today), to: toLocalISODate(addDays(today, 2)) };
  // Football's weekend runs Friday night to Sunday. Once it has started, start today.
  const weekday = today.getDay(); // 0 = Sunday
  const daysToSunday = (7 - weekday) % 7;
  const start = weekday === 0 || weekday >= 5 ? today : addDays(today, 5 - weekday);
  return { from: toLocalISODate(start), to: toLocalISODate(addDays(today, daysToSunday)) };
}

const WINDOWS: { value: WindowKey; label: string }[] = [
  // Short labels so all three fit the rail; the exact dates show underneath.
  { value: "next2", label: "2 days" },
  { value: "weekend", label: "Weekend" },
  { value: "next3", label: "3 days" },
];
const TARGETS = [1.5, 2, 3, 5] as const;
const LEG_OPTIONS = [3, 4, 5, 6] as const;
const QUICK_PICKS = [2, 4, 6] as const;

const legKey = (leg: StrongLegView) => `${leg.fixture_id}|${leg.label}`;

function product(values: (number | null)[]): number | null {
  if (values.length === 0 || values.some((v) => v === null)) return null;
  return values.reduce<number>((acc, v) => acc * (v as number), 1);
}

function Evidence({ leg }: { leg: StrongLegView }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] tabular-nums text-faint">
      <span className="font-semibold text-success">
        Form {leg.hits}/{leg.sample}
      </span>
      {leg.h2h_sample > 0 && (
        <span>
          H2H {leg.h2h_hits}/{leg.h2h_sample}
        </span>
      )}
      {leg.book_implied_prob !== null && <span>Book {formatPercent(leg.book_implied_prob)}</span>}
      {leg.model_prob !== null && <span className="text-accent">Model {formatPercent(leg.model_prob)}</span>}
    </div>
  );
}

function LegRow({
  leg,
  action,
  pick,
}: {
  leg: StrongLegView;
  action?: { kind: "add" | "remove"; onClick: () => void };
  /** A share checkbox, for the unpriced list where there's no slip to add to. */
  pick?: { selected: boolean; onToggle: () => void };
}) {
  return (
    <div className="flex items-start justify-between gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-ink">
          {leg.home_team} vs {leg.away_team}
        </p>
        <p className="mt-0.5 text-[11px] text-faint">
          {formatKickoff(leg.kickoff_utc)}
          {leg.league ? ` · ${leg.league}` : ""}
        </p>
        <p className="mt-1 text-[12px] font-semibold text-accent">{leg.label}</p>
        <Evidence leg={leg} />
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {leg.offered_odds !== null ? (
          <span className="text-[15px] font-bold tabular-nums text-ink">{formatOdds(leg.offered_odds)}</span>
        ) : (
          // Plain text, not a dash: a lone "—" beside these rows reads as a remove button.
          <span className="text-[11px] font-medium text-faint">no price</span>
        )}
        {action && (
          <button
            type="button"
            onClick={action.onClick}
            aria-label={action.kind === "add" ? "Add to slip" : "Remove from slip"}
            className="flex h-11 w-11 items-center justify-center rounded-lg border border-border text-muted transition-colors duration-150 hover:border-outline hover:bg-subtle hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:h-8 sm:w-8"
          >
            {action.kind === "add" ? <Plus size={14} /> : <Minus size={14} />}
          </button>
        )}
        {pick && (
          <button
            type="button"
            role="checkbox"
            aria-checked={pick.selected}
            onClick={pick.onToggle}
            aria-label={`Share ${leg.home_team} vs ${leg.away_team}`}
            className={`flex h-11 w-11 items-center justify-center rounded-lg border transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:h-8 sm:w-8 ${
              pick.selected
                ? "border-accent bg-accent-light text-accent"
                : "border-border text-transparent hover:border-outline hover:bg-subtle"
            }`}
          >
            <Check size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  hint,
  className = "",
  children,
}: {
  title: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`overflow-hidden rounded-xl border border-border bg-surface shadow-raised ${className}`}>
      <div className="border-b border-border bg-subtle px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">{title}</p>
        {hint && <p className="mt-0.5 text-[11px] text-faint">{hint}</p>}
      </div>
      <div className="divide-y divide-hairline">{children}</div>
    </div>
  );
}

function SummaryRow({ label, value, tone = "text-ink" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`text-lg font-bold tabular-nums ${tone}`}>{value}</dd>
    </div>
  );
}

export function StrongSlip() {
  const [windowKey, setWindowKey] = useState<WindowKey>("weekend");
  const [target, setTarget] = useState<number>(2);
  const [maxLegs, setMaxLegs] = useState<number>(5);
  const { from, to } = windowRange(windowKey);

  const query = useQuery<StrongSlipView>({
    queryKey: ["strong-acca", from, to, target, maxLegs],
    queryFn: () => fetchStrongAcca({ from, to, targetOdds: target, maxLegs }),
    staleTime: 60_000,
  });
  const data = query.data;

  // The user's edits to the suggested slip; reset whenever a new suggestion loads.
  const [edited, setEdited] = useState<{ source: StrongSlipView; legs: StrongLegView[] } | null>(null);
  const legs = data ? (edited?.source === data ? edited.legs : data.legs) : [];
  const setLegs = (next: StrongLegView[]) => data && setEdited({ source: data, legs: next });
  // Unpriced picks ticked for sharing; same reset-on-new-suggestion rule as the slip.
  const [shareSel, setShareSel] = useState<{ source: StrongSlipView; keys: Set<string> } | null>(null);
  const shareKeys = data && shareSel?.source === data ? shareSel.keys : new Set<string>();
  const setShareKeys = (keys: Set<string>) => data && setShareSel({ source: data, keys });
  const toggleShare = (leg: StrongLegView) => {
    const next = new Set(shareKeys);
    if (!next.delete(legKey(leg))) next.add(legKey(leg));
    setShareKeys(next);
  };
  const unpriced = data?.unpriced ?? [];
  const sharedUnpriced = unpriced.filter((l) => shareKeys.has(legKey(l)));
  // "Top N" is active when exactly the first N are ticked; the list is strongest first.
  const isTop = (n: number) => shareKeys.size === n && unpriced.slice(0, n).every((l) => shareKeys.has(legKey(l)));
  const quickPicks = [
    ...QUICK_PICKS.filter((n) => n < unpriced.length).map((n) => ({ n, label: `Top ${n}` })),
    { n: unpriced.length, label: `All ${unpriced.length}` },
  ];
  const [stake, setStake] = useState("0");
  const [savedFor, setSavedFor] = useState<StrongLegView[] | null>(null);

  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: createSlip,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["slips"] });
      setSavedFor(legs);
    },
  });

  const chosen = new Set(legs.map((l) => l.fixture_id));
  const pool = data
    ? [...data.legs, ...data.alternatives].filter((l) => !chosen.has(l.fixture_id))
    : [];
  const priced = legs.filter((l) => l.offered_odds !== null);
  const odds = priced.length ? combinedOdds(priced.map((l) => l.offered_odds as number)) : 0;
  const bookProb = product(legs.map((l) => l.book_implied_prob));
  const modelProb = product(legs.map((l) => l.model_prob));
  const stakeValue = Number(stake);
  const stakeValid = Number.isFinite(stakeValue) && stakeValue >= 0;

  function handleSave() {
    save.mutate({
      name: `Strong slip · ${from === to ? from : `${from} → ${to}`}`,
      stake: stakeValue,
      currency: "ZAR",
      legs: priced.map((l) => ({
        fixture_id: l.fixture_id,
        home_team: l.home_team,
        away_team: l.away_team,
        kickoff_utc: l.kickoff_utc,
        league: l.league,
        provider: l.provider,
        market_type: l.market_type,
        selection: l.selection,
        point: l.point,
        price: l.offered_odds as number,
      })),
    });
  }

  return (
    /*
      Phones get one column: controls, slip, summary, alternatives, unpriced,
      note — set by `order`, because the column wrappers below are
      `display: contents` until `xl`. From `xl` the short controls and the
      slip summary share a sticky rail, so the space under the controls holds
      the numbers you act on while the pick lists scroll beside it; from `2xl`
      the lists split into two columns.
    */
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 xl:mx-0 xl:grid xl:max-w-none xl:grid-cols-[20rem_minmax(0,1fr)] xl:items-start xl:gap-6 2xl:grid-cols-[22rem_minmax(0,1fr)]">
      <div className="contents xl:sticky xl:top-6 xl:flex xl:flex-col xl:gap-4">
        <div className="order-1 flex flex-col gap-4 rounded-2xl border border-border bg-surface p-5 shadow-panel">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <Flame className="h-4 w-4 text-accent" />
              <h2 className="text-sm font-semibold text-ink">Strong Slip</h2>
            </div>
            <p className="text-xs text-faint">
              The most consistent form lines across the window, stacked until the slip
              reaches your price.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-faint">Window</p>
            <SegmentedControl label="Window" value={windowKey} onChange={setWindowKey} segments={WINDOWS} fill />
            <p className="text-[11px] text-faint tabular-nums">
              {from === to ? from : `${from} → ${to}`}
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-faint">Target odds</p>
            <SegmentedControl
              label="Target odds"
              value={target}
              onChange={setTarget}
              segments={TARGETS.map((t) => ({ value: t, label: formatOdds(t) }))}
              fill
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-faint">Max legs</p>
            <SegmentedControl
              label="Max legs"
              value={maxLegs}
              onChange={setMaxLegs}
              segments={LEG_OPTIONS.map((n) => ({ value: n, label: String(n) }))}
              fill
            />
          </div>
        </div>

        {legs.length > 0 && (
          <div className="order-3 flex flex-col gap-3 rounded-2xl border border-border bg-surface p-5 shadow-panel">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">
              Your slip · {legs.length} leg{legs.length === 1 ? "" : "s"}
            </p>
            <dl className="divide-y divide-hairline">
              <SummaryRow label="Combined odds" value={formatOdds(odds)} />
              <SummaryRow label="Bookmaker's chance" value={bookProb !== null ? formatPercent(bookProb) : "—"} />
              <SummaryRow
                label="Model's chance"
                value={modelProb !== null ? formatPercent(modelProb) : "—"}
                tone="text-accent"
              />
            </dl>
            {modelProb === null && (
              <p className="-mt-1 text-[11px] text-faint">
                The model only prices the 2.5 goals line, so it can&apos;t rate every leg.
              </p>
            )}

            {savedFor === legs ? (
              <div className="flex items-center gap-2 rounded-xl border border-success-soft bg-success-faint px-4 py-3">
                <CheckCircle className="h-4 w-4 shrink-0 text-success" />
                <p className="text-sm font-medium text-success-deeper">Saved to My Slips</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <label className="flex flex-col gap-1 text-[11px] font-semibold uppercase tracking-widest text-faint">
                  Stake (R) · 0 = paper
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="any"
                    value={stake}
                    onChange={(e) => setStake(e.target.value)}
                    className="min-h-[48px] w-full rounded-xl border border-border bg-surface px-3 text-base font-medium normal-case tracking-normal text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[44px] sm:text-sm"
                  />
                </label>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={save.isPending || !stakeValid || priced.length === 0}
                  className="flex min-h-[48px] items-center justify-center gap-2 rounded-xl border border-accent bg-accent-light px-5 text-sm font-semibold text-accent transition-all duration-150 hover:bg-accent-line focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-[44px]"
                >
                  {save.isPending ? (
                    <>
                      <Spinner size="sm" />
                      Saving…
                    </>
                  ) : (
                    "Save to My Slips"
                  )}
                </button>
              </div>
            )}
            {save.isError && (
              <p className="rounded-xl border border-danger-soft bg-danger-faint px-4 py-2.5 text-sm text-danger">
                {(save.error as Error).message}
              </p>
            )}
            <ShareSlip title="Strong slip" legs={legs} />
          </div>
        )}
      </div>

      <div className="contents xl:grid xl:grid-cols-1 xl:items-start xl:gap-4 2xl:grid-cols-2">
        <div className="contents xl:flex xl:flex-col xl:gap-4">
          {query.isPending && (
            <div className="order-2 flex items-center justify-center gap-2 rounded-xl border border-dashed border-border px-5 py-12 text-sm text-faint">
              <Spinner size="sm" />
              Reading form across the window…
            </div>
          )}
          {query.isError && (
            <div className="order-2 rounded-xl border border-danger-soft bg-danger-faint px-4 py-3 text-sm text-danger">
              Couldn&apos;t build the Strong slip. {(query.error as Error).message}
            </div>
          )}
          {data && (
            <div className="order-2 flex flex-col gap-3">
              <p className={`text-sm ${data.target_met ? "text-muted" : "text-warn-strong"}`}>{data.note}</p>
              {legs.length > 0 ? (
                <Section title={`${legs.length}-leg Strong slip`}>
                  {legs.map((leg) => (
                    <LegRow
                      key={legKey(leg)}
                      leg={leg}
                      action={{ kind: "remove", onClick: () => setLegs(legs.filter((l) => l !== leg)) }}
                    />
                  ))}
                </Section>
              ) : (
                <div className="rounded-xl border border-border bg-canvas px-5 py-10 text-center text-sm text-faint">
                  No priced Strong legs in this window.
                </div>
              )}
            </div>
          )}
          {pool.length > 0 && (
            <Section className="order-4" title="Other Strong picks" hint="Tap + to add one to the slip.">
              {pool.map((leg) => (
                <LegRow
                  key={legKey(leg)}
                  leg={leg}
                  action={{ kind: "add", onClick: () => setLegs([...legs, leg]) }}
                />
              ))}
            </Section>
          )}
        </div>

        <div className="contents xl:flex xl:flex-col xl:gap-4">
          {unpriced.length > 0 && (
            <Section
              className="order-5"
              title="Strong, but no price collected"
              hint="Mostly Over 1.5 lines our odds feed doesn't carry. Check the price at your bookmaker. Tick any to share them."
            >
              {/* Share controls sit above the list, not below 20-odd rows. */}
              <div className="flex flex-col gap-3 px-4 py-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  {quickPicks.map(({ n, label }) => (
                    <button
                      key={label}
                      type="button"
                      aria-pressed={isTop(n)}
                      onClick={() => setShareKeys(new Set(unpriced.slice(0, n).map(legKey)))}
                      className={`min-h-[44px] rounded-lg border px-3 text-xs font-semibold transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[32px] ${
                        isTop(n)
                          ? "border-accent/40 bg-accent-light text-accent ring-1 ring-accent/20"
                          : "border-border bg-surface text-muted hover:border-outline"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                  {shareKeys.size > 0 && (
                    <button
                      type="button"
                      onClick={() => setShareKeys(new Set())}
                      className="min-h-[44px] rounded-lg px-3 text-xs font-medium text-muted transition-colors duration-150 hover:bg-hairline hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[32px]"
                    >
                      Clear
                    </button>
                  )}
                  <span className="ml-auto text-[11px] tabular-nums text-faint">{shareKeys.size} selected</span>
                </div>
                <ShareSlip title="Strong picks" legs={sharedUnpriced} />
              </div>
              {unpriced.map((leg) => (
                <LegRow
                  key={legKey(leg)}
                  leg={leg}
                  pick={{ selected: shareKeys.has(legKey(leg)), onToggle: () => toggleShare(leg) }}
                />
              ))}
            </Section>
          )}
          {data && (
            <div className="order-6 rounded-xl border border-border bg-subtle px-4 py-3.5">
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
                <div className="flex flex-col gap-1">
                  <p className="text-xs font-semibold text-warn-strong">Honest note</p>
                  <p className="text-[12px] leading-relaxed text-warn-deep">
                    &ldquo;Strong&rdquo; means both sides&apos; recent matches landed the line at
                    least 8 times in 10 — a record of what happened, not a probability. Every
                    leg has to land. &ldquo;Bookmaker&apos;s chance&rdquo; is the market&apos;s
                    own view of the slip; when Form says 10/10 but the book says 80%, the price
                    already knows.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
