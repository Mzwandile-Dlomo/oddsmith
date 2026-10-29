import type {
  AccaView,
  CalendarView,
  BacktestView,
  CornerEvaluationReportView,
  DailyAccaView,
  EvaluationReportView,
  Fixture,
  HistoryMatch,
  LeagueTableView,
  LegCreate,
  MarketType,
  MatchInsights,
  MatchReadView,
  ModelReadinessView,
  PaperPerformanceView,
  PipelineHealthView,
  PersonalPoolEntry,
  PersonalPoolView,
  ResearchDay,
  SlipCreate,
  SlipUpdate,
  SlipView,
  StrongSlipView,
  TeamStatsView,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8137";

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

/** Stored fixtures only — the scheduled sync fills the DB, browsing never spends quota. */
export async function fetchFixtures(
  dateFrom?: string,
  dateTo?: string
): Promise<Fixture[]> {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  params.set("model", "true");
  const qs = params.toString();
  return request<Fixture[]>(`/fixtures${qs ? `?${qs}` : ""}`);
}

export async function fetchFixtureMarkets(
  fixtureId: string
): Promise<Fixture> {
  return request<Fixture>(`/fixtures/${fixtureId}/markets`);
}

export async function fetchFixtureInsights(
  fixtureId: string,
  last = 5
): Promise<MatchInsights> {
  return request<MatchInsights>(
    `/fixtures/${encodeURIComponent(fixtureId)}/insights?last=${last}`
  );
}

export async function createSlip(body: SlipCreate): Promise<SlipView> {
  return request<SlipView>("/slips", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchSlips(): Promise<SlipView[]> {
  return request<SlipView[]>("/slips");
}

export async function fetchPersonalPool(): Promise<PersonalPoolView> {
  return request<PersonalPoolView>("/personal-pool");
}

export async function addPersonalPoolEntry(body: LegCreate): Promise<PersonalPoolEntry> {
  return request<PersonalPoolEntry>("/personal-pool", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchSlip(id: number): Promise<SlipView> {
  return request<SlipView>(`/slips/${id}`);
}

export async function updateSlip(
  id: number,
  body: SlipUpdate
): Promise<SlipView> {
  return request<SlipView>(`/slips/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function fetchWeekendAcca(legs: number): Promise<AccaView> {
  return request<AccaView>(`/acca/weekend?legs=${legs}`);
}

/** `from`/`to` are local `YYYY-MM-DD` days, inclusive. */
export async function fetchStrongAcca({
  from,
  to,
  targetOdds,
  maxLegs,
}: {
  from: string;
  to: string;
  targetOdds: number;
  maxLegs: number;
}): Promise<StrongSlipView> {
  const params = new URLSearchParams({
    date_from: from,
    date_to: to,
    target_odds: String(targetOdds),
    max_legs: String(maxLegs),
  });
  return request<StrongSlipView>(`/acca/strong?${params.toString()}`);
}

export async function fetchBacktest(): Promise<BacktestView> {
  return request<BacktestView>("/model/backtest");
}

export async function fetchModelReadiness(): Promise<ModelReadinessView> {
  return request<ModelReadinessView>("/model/readiness");
}

export async function fetchPaperPerformance(): Promise<PaperPerformanceView> {
  return request<PaperPerformanceView>("/model/paper-performance");
}

export async function fetchPipelineHealth(): Promise<PipelineHealthView> {
  return request<PipelineHealthView>("/health/pipeline");
}

export async function fetchLatestEvaluation(): Promise<EvaluationReportView> {
  return request<EvaluationReportView>("/model/evaluation/latest");
}

export async function fetchLatestCornerEvaluation(): Promise<CornerEvaluationReportView> {
  return request<CornerEvaluationReportView>("/model/corners/evaluation/latest");
}

export interface DailyAccaParams {
  targetOdds: number;
  maxLegs: number;
  bankroll: number;
  horizonBets: number;
  markets: MarketType[];
  /** Archive the untouched canonical 1.50 prediction once for the day. */
  autoTrack?: boolean;
  /** ISO date (YYYY-MM-DD). Omit for "from now"; set to scope the slip to one day. */
  date?: string;
}

export async function fetchDailyAcca({
  targetOdds,
  maxLegs,
  bankroll,
  horizonBets,
  markets,
  date,
  autoTrack = false,
}: DailyAccaParams): Promise<DailyAccaView> {
  const params = new URLSearchParams({
    target_odds: String(targetOdds),
    max_legs: String(maxLegs),
    bankroll: String(bankroll),
    horizon_bets: String(horizonBets),
  });
  if (date) {
    // The viewer's day, not UTC's: a date-time with no offset parses as local
    // time, so this sends local midnight to 23:59:59 as UTC instants.
    params.set("date_from", new Date(`${date}T00:00:00`).toISOString());
    params.set("date_to", new Date(`${date}T23:59:59`).toISOString());
  }
  if (autoTrack) params.set("auto_track", "true");
  markets.forEach((market) => params.append("markets", market));
  return request<DailyAccaView>(`/acca/daily?${params.toString()}`);
}

export async function fetchCalendar(
  dateFrom: string,
  dateTo: string,
  includeModel = true
): Promise<CalendarView> {
  const params = new URLSearchParams({
    date_from: dateFrom,
    date_to: dateTo,
    include_model: String(includeModel),
  });
  return request<CalendarView>(`/calendar?${params.toString()}`);
}

export async function fetchHistoryLeagues(): Promise<string[]> {
  return request<string[]>("/history/leagues");
}

export async function fetchHistoryMatches(
  league?: string,
  team?: string,
  limit = 50,
  offset = 0
): Promise<HistoryMatch[]> {
  const params = new URLSearchParams();
  if (league) params.set("league", league);
  if (team) params.set("team", team);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return request<HistoryMatch[]>(`/history/matches?${params.toString()}`);
}

export async function fetchTeamStats(
  team: string,
  league?: string
): Promise<TeamStatsView> {
  const params = new URLSearchParams();
  if (league) params.set("league", league);
  const qs = params.toString();
  return request<TeamStatsView>(
    `/history/teams/${encodeURIComponent(team)}/stats${qs ? `?${qs}` : ""}`
  );
}

export async function fetchLeagueTable(league: string, season?: number): Promise<LeagueTableView> {
  const params = new URLSearchParams({ league });
  if (season !== undefined) params.set("season", String(season));
  return request<LeagueTableView>(`/history/table?${params.toString()}`);
}

/** Every stored fixture between two instants (a local day), with form and graded angles. */
export async function fetchResearchDay(fromIso: string, toIso: string): Promise<ResearchDay> {
  const params = new URLSearchParams({ date_from: fromIso, date_to: toIso });
  return request<ResearchDay>(`/research/day?${params.toString()}`);
}

/** Computed angles plus Claude's cached written read for one match. */
export async function fetchMatchRead(fixtureId: string): Promise<MatchReadView> {
  return request<MatchReadView>(`/fixtures/${encodeURIComponent(fixtureId)}/read`);
}
