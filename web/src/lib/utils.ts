import type { LegResult, MarketType, SlipResult } from "./types";

export function formatOdds(price: number): string {
  return price.toFixed(2);
}

export function formatCurrency(
  amount: number,
  currency = "USD"
): string {
  return `${currency} ${amount.toFixed(2)}`;
}

export function formatKickoff(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatKickoffShort(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleString(undefined, {
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
      return "text-emerald-700";
    case "lost":
      return "text-red-600";
    case "void":
      return "text-gray-400";
    default:
      return "text-amber-600";
  }
}

export function resultBadgeClass(result: LegResult | SlipResult): string {
  switch (result) {
    case "won":
      return "bg-[#D1FAE5] text-[#059669] border-[#059669]/20";
    case "lost":
      return "bg-[#FEE2E2] text-[#DC2626] border-[#DC2626]/20";
    case "void":
      return "bg-gray-100 text-gray-500 border-gray-200";
    default:
      return "bg-[#FEF3C7] text-[#D97706] border-[#D97706]/20";
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
