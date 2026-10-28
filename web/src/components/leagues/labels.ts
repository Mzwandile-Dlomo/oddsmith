/**
 * Football-Data's league keys hold the long-run history (about 5,000 matches
 * each); API-Football's names ("Premier League", "Serie A") only hold a handful
 * of recent results. Lead with the big five under readable names.
 */
export const MAIN_LEAGUES: { key: string; label: string }[] = [
  { key: "EPL", label: "Premier League" },
  { key: "LaLiga", label: "La Liga" },
  { key: "SerieA", label: "Serie A" },
  { key: "Bundesliga", label: "Bundesliga" },
  { key: "Ligue1", label: "Ligue 1" },
];

export function leagueLabel(key: string): string {
  return MAIN_LEAGUES.find((l) => l.key === key)?.label ?? key;
}

/** "2026" → "2026/27": stored seasons are keyed by their starting year. */
export function seasonLabel(season: number): string {
  return `${season}/${String((season + 1) % 100).padStart(2, "0")}`;
}
