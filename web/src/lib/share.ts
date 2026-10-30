import { formatKickoff, formatOdds } from "./utils";

/** The fields every pick type has in common — enough to rebuild the bet at a bookmaker. */
export interface ShareLeg {
  home_team: string;
  away_team: string;
  kickoff_utc: string | null;
  league: string | null;
  market_type: string;
  selection: string;
  point: number | null;
  offered_odds: number | null;
  /** A ready-made label (Strong legs carry one); otherwise built from the market. */
  label?: string;
}

/**
 * Spelled out the way a bookmaker's market list reads, not the app's compact
 * "1X2 / O/U" chips — a friend has to find this market on Betway, not here.
 */
export function shareSelection(leg: ShareLeg): string {
  if (leg.label) return leg.label;
  const line = leg.point !== null ? ` ${leg.point}` : "";
  switch (leg.market_type) {
    case "match_winner":
      if (leg.selection === "Home") return `${leg.home_team} to win`;
      if (leg.selection === "Away") return `${leg.away_team} to win`;
      return "Draw";
    case "btts":
      return `Both teams to score: ${leg.selection}`;
    case "over_under":
      return `${leg.selection}${line} goals`;
    case "corner_totals":
      return `${leg.selection}${line} corners`;
    case "double_chance":
      return `Double chance: ${leg.selection}`;
    default:
      return `${leg.selection}${line}`;
  }
}

/**
 * Plain text for WhatsApp and the like. `*bold*` is WhatsApp's markup and
 * reads fine as plain asterisks anywhere else. Ends with when the prices were
 * read and that every leg has to land: odds move, and a shared slip shouldn't
 * read as a sure thing.
 */
export function formatSlipText(title: string, legs: ShareLeg[]): string {
  const lines = [`*${title}* · ${legs.length} leg${legs.length === 1 ? "" : "s"}`, ""];

  legs.forEach((leg, i) => {
    lines.push(`${i + 1}. ${leg.home_team} vs ${leg.away_team}`);
    const when = [leg.kickoff_utc ? formatKickoff(leg.kickoff_utc) : null, leg.league]
      .filter(Boolean)
      .join(" · ");
    if (when) lines.push(`   ${when}`);
    const price = leg.offered_odds !== null ? `@ ${formatOdds(leg.offered_odds)}` : "(check price)";
    lines.push(`   ➜ *${shareSelection(leg)}* ${price}`);
    lines.push("");
  });

  const prices = legs.map((l) => l.offered_odds);
  if (prices.every((p) => p !== null)) {
    const combined = (prices as number[]).reduce((acc, p) => acc * p, 1);
    lines.push(`*Combined odds: ${formatOdds(combined)}*`);
  } else if (prices.every((p) => p === null)) {
    lines.push("No prices collected yet. Check each one at your bookmaker.");
  } else {
    lines.push("Some legs have no price yet. Check them at your bookmaker.");
  }

  const readAt = new Date().toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
  const asOf = prices.some((p) => p !== null) ? `Prices as of ${readAt}; they move. ` : "";
  lines.push(`_${asOf}Every leg has to land._`);
  return lines.join("\n");
}
