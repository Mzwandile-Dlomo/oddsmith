import type { LegResult, MarketType, SlipResult } from "./types";

export function formatOdds(price: number): string {
  return price.toFixed(2);
}

export function formatCurrency(
  amount: number,
  currency = "ZAR"
): string {
  return `${currency === "ZAR" ? "R" : currency} ${amount.toFixed(2)}`;
}

/**
 * The API sends naive UTC timestamps — "2026-08-28T22:00:00", no offset — and
 * `new Date` reads a date-time with no offset as *local* time. Left alone,
 * every kickoff renders shifted by the viewer's UTC offset. Put back the "Z"
 * the payload leaves off.
 */
export function parseKickoff(isoString: string): Date {
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(isoString);
  return new Date(hasZone ? isoString : `${isoString}Z`);
}

/**
 * Whether a fixture should have a known result by now: kickoff plus roughly a
 * full match and stoppage. Before that the outcome genuinely isn't in yet.
 */
export const MATCH_DURATION_MS = 2 * 60 * 60 * 1000;

export function hasFinished(kickoffUtc: string, now: number = Date.now()): boolean {
  return now > parseKickoff(kickoffUtc).getTime() + MATCH_DURATION_MS;
}

export function formatKickoff(isoString: string): string {
  return parseKickoff(isoString).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatKickoffShort(isoString: string): string {
  return parseKickoff(isoString).toLocaleString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  });
}

export function legLabel(
  marketType: string,
  selection: string,
  point: number | null,
  homeTeam: string,
  awayTeam: string
): string {
  if (marketType === "match_winner") {
    if (selection === "Home") return `${homeTeam} (Home)`;
    if (selection === "Away") return `${awayTeam} (Away)`;
    return "Draw";
  }
  if (marketType === "btts") {
    return `BTTS: ${selection}`;
  }
  if (marketType === "over_under") {
    return `${selection} ${point !== null ? point : ""}`.trim();
  }
  return selection;
}

export function outcomeLabel(
  marketType: MarketType,
  outcomeName: string,
  point: number | null,
  homeTeam: string,
  awayTeam: string
): string {
  return legLabel(marketType, outcomeName, point, homeTeam, awayTeam);
}

export function marketLabel(type: MarketType): string {
  switch (type) {
    case "match_winner":
      return "Match Winner";
    case "btts":
      return "Both Teams to Score";
    case "over_under":
      return "Over / Under";
    case "corner_totals":
      return "Total Corners";
    case "double_chance":
      return "Double Chance";
    default:
      return type;
  }
}

export function combinedOdds(prices: number[]): number {
  if (prices.length === 0) return 1;
  return prices.reduce((acc, p) => acc * p, 1);
}

export function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

export function toISODate(date: Date): string {
  return date.toISOString().split("T")[0];
}

export function resultColor(result: LegResult | SlipResult): string {
  switch (result) {
    case "won":
      return "text-success-deep";
    case "lost":
      return "text-danger";
    case "void":
      return "text-faint";
    default:
      return "text-warn";
  }
}

export function resultBadgeClass(result: LegResult | SlipResult): string {
  switch (result) {
    case "won":
      return "bg-success-soft text-success border-success/20";
    case "lost":
      return "bg-danger-soft text-danger border-danger/20";
    case "void":
      return "bg-hairline text-muted border-border";
    default:
      return "bg-warn-soft text-warn border-warn/20";
  }
}

export function groupFixturesByDay<T extends { kickoff_utc: string }>(
  fixtures: T[]
): { label: string; isoDate: string; items: T[] }[] {
  const now = new Date();
  const todayStr = toISODate(now);
  const tomorrowStr = toISODate(addDays(now, 1));

  const groups = new Map<string, T[]>();
  for (const f of fixtures) {
    const iso = f.kickoff_utc.split("T")[0];
    if (!groups.has(iso)) groups.set(iso, []);
    groups.get(iso)!.push(f);
  }

  const sorted = Array.from(groups.entries()).sort(([a], [b]) =>
    a.localeCompare(b)
  );

  return sorted.map(([isoDate, items]) => {
    let label: string;
    if (isoDate === todayStr) {
      label = "Today";
    } else if (isoDate === tomorrowStr) {
      label = "Tomorrow";
    } else {
      const d = new Date(isoDate + "T12:00:00");
      label = d.toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
    }
    return { label, isoDate, items };
  });
}

// --------------------------------------------------------------------------
// Calendar
//
// Day keys are plain `YYYY-MM-DD` strings in the user's local timezone. Dates
// are constructed at local noon so a DST shift can never roll a cell onto the
// neighbouring day.
// --------------------------------------------------------------------------

export function dateFromISO(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d, 12, 0, 0);
}

export function toLocalISODate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function todayISO(): string {
  return toLocalISODate(new Date());
}

export function addMonths(iso: string, delta: number): string {
  const d = dateFromISO(iso);
  return toLocalISODate(new Date(d.getFullYear(), d.getMonth() + delta, 1, 12));
}

export function monthLabel(iso: string): string {
  return dateFromISO(iso).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

export function dayLabel(iso: string): string {
  const today = todayISO();
  if (iso === today) return "Today";
  if (iso === toLocalISODate(addDays(dateFromISO(today), 1))) return "Tomorrow";
  if (iso === toLocalISODate(addDays(dateFromISO(today), -1))) return "Yesterday";
  return dateFromISO(iso).toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

/** The Monday-first 6x7 grid covering the month `iso` falls in. */
export function monthGrid(iso: string): string[] {
  const anchor = dateFromISO(iso);
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1, 12);
  // getDay() is Sunday-0; shift so Monday starts the week.
  const lead = (first.getDay() + 6) % 7;
  const start = addDays(first, -lead);
  return Array.from({ length: 42 }, (_, i) => toLocalISODate(addDays(start, i)));
}

export function isSameMonth(iso: string, monthIso: string): boolean {
  return iso.slice(0, 7) === monthIso.slice(0, 7);
}

export function formatSignedCurrency(amount: number, currency = "ZAR"): string {
  const sign = amount > 0 ? "+" : amount < 0 ? "−" : "";
  return `${sign}${currency === "ZAR" ? "R" : currency} ${Math.abs(amount).toFixed(2)}`;
}

export function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/**
 * Signed amount with the currency dropped and thousands abbreviated, for
 * places too narrow for the full string — calendar cells, mobile chips.
 */
export function formatCompactSigned(amount: number): string {
  const sign = amount > 0 ? "+" : amount < 0 ? "−" : "";
  const abs = Math.abs(amount);
  if (abs >= 1000) return `${sign}${(abs / 1000).toFixed(1)}k`;
  // Whole numbers are the common case and read better without ".00".
  return `${sign}${Number.isInteger(abs) ? abs : abs.toFixed(2)}`;
}

/** Signed percentage, e.g. 0.0421 → "+4.2%". Input is a ratio, not a percent. */
export function formatSignedPercent(value: number, digits = 1): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value * 100).toFixed(digits)}%`;
}
