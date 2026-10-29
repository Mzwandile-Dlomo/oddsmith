export type MarketType =
  | "match_winner"
  | "btts"
  | "over_under"
  | "corner_totals"
  | "double_chance";
export type LegResult = "pending" | "won" | "lost" | "void";
export type SlipResult = "pending" | "won" | "lost";

export interface Outcome {
  name: string;
  price: number;
  point: number | null;
}

export interface Market {
  type: MarketType;
  outcomes: Outcome[];
  bookmaker: string | null;
  provider: string | null;
}

export interface ModelOutcome {
  name: string;
  model_prob: number;
  model_odds: number;
  bookmaker_odds: number | null;
  edge: number | null;
  expected_value: number | null;
  is_value: boolean;
  point: number | null;
}

export interface ModelMarket {
  type: MarketType;
  outcomes: ModelOutcome[];
}

export interface Fixture {
  id: string;
  home_team: string;
  away_team: string;
  kickoff_utc: string;
  league: string | null;
  provider: string;
  markets: Market[];
  model_markets: ModelMarket[];
}

export interface AccaLegView {
  fixture_id: string;
  home_team: string;
  away_team: string;
  kickoff_utc: string | null;
  league: string | null;
  provider: string;
  market_type: string;
  selection: string;
  point: number | null;
  offered_odds: number;
  model_prob: number;
  edge: number;
  expected_value: number;
}

export interface AccaView {
  legs: AccaLegView[];
  combined_odds: number;
  combined_model_prob: number;
  combined_expected_value: number;
}

export interface BacktestView {
  matches_scored: number;
  hit_rate: number;
  brier: number;
  // Null unless the backtest was given historical bookmaker odds to simulate against.
  roi: number | null;
  value_bets: number;
  note: string;
}

export interface DataCoverageView {
  key: string;
  label: string;
  records: number;
  percent: number;
}

export interface LeagueCoverageView {
  league: string;
  matches: number;
  date_from: string;
  date_to: string;
}

export interface MarketReadinessView {
  key: string;
  label: string;
  stage: "baseline" | "research" | "blocked";
  prediction_ready: boolean;
  roi_validated: boolean;
  training_rows: number;
  odds_rows: number;
  settled_rows: number;
  note: string;
}

export interface ModelReadinessView {
  model_name: string;
  model_stage: string;
  model_trained: boolean;
  dataset_matches: number;
  baseline_matches: number;
  leagues: number;
  seasons: number;
  date_from: string | null;
  date_to: string | null;
  freshness_days: number | null;
  price_snapshots: number;
  coverage: DataCoverageView[];
  league_coverage: LeagueCoverageView[];
  markets: MarketReadinessView[];
  next_priorities: string[];
}

export interface PaperPerformanceView {
  generated_tickets: number;
  pending_tickets: number;
  settled_tickets: number;
  won_tickets: number;
  lost_tickets: number;
  win_rate: number | null;
  average_odds: number | null;
  unit_staked: number;
  unit_returned: number;
  unit_profit: number;
  unit_roi: number | null;
  tracking_target: number;
  note: string;
  calibration: PaperCalibrationView;
}

export interface CalibrationBucketView {
  label: string;
  legs: number;
  predicted_rate: number | null;
  actual_rate: number | null;
}

/** Predicted vs actual for paper legs whose probability was stored at save time. */
export interface PaperCalibrationView {
  graded_legs: number;
  /** Settled legs from tickets saved before probabilities were stored. */
  ungraded_legs: number;
  expected_hits: number;
  expected_hits_low: number;
  expected_hits_high: number;
  actual_hits: number;
  graded_tickets: number;
  expected_ticket_wins: number;
  actual_ticket_wins: number;
  buckets: CalibrationBucketView[];
  verdict: string;
}

export interface PipelineHealthView {
  checked_at: string;
  last_odds_capture_at: string | null;
  last_result_at: string | null;
  upcoming_fixtures: number;
  overdue_paper_legs: number;
  healthy: boolean;
  problems: string[];
}

export interface ProbabilityMetricsView {
  matches: number;
  accuracy: number;
  log_loss: number;
  brier: number;
  calibration_error: number;
}

export interface StrategyMetricsView {
  bets: number;
  wins: number;
  profit: number;
  roi: number | null;
  roi_ci_low: number | null;
  roi_ci_high: number | null;
}

export interface EvaluationSummaryView {
  model: ProbabilityMetricsView;
  market: ProbabilityMetricsView;
  strategy: StrategyMetricsView;
}

export interface FoldEvaluationView {
  league: string;
  test_season: number;
  train_matches: number;
  test_matches: number;
  summary: EvaluationSummaryView;
}

export interface LeagueEvaluationView {
  league: string;
  seasons: number;
  folds: FoldEvaluationView[];
  summary: EvaluationSummaryView;
}

export interface EvaluationReportView {
  generated_at: string;
  model_name: string;
  min_train_seasons: number;
  min_edge: number;
  max_edge: number;
  leagues: LeagueEvaluationView[];
  overall: EvaluationSummaryView;
}

export interface CornerMetricsView {
  matches: number;
  mean_actual: number;
  mean_prediction: number;
  mae: number;
  rmse: number;
  poisson_deviance: number;
}

export interface CornerSummaryView {
  model: CornerMetricsView;
  baseline: CornerMetricsView;
  mae_improvement: number;
  improvement_ci_low: number | null;
  improvement_ci_high: number | null;
}

export interface CornerLeagueEvaluationView {
  league: string;
  seasons: number;
  folds: Array<{
    league: string;
    test_season: number;
    train_matches: number;
    test_matches: number;
    summary: CornerSummaryView;
  }>;
  summary: CornerSummaryView;
}

export interface CornerEvaluationReportView {
  generated_at: string;
  model_name: string;
  min_train_seasons: number;
  leagues: CornerLeagueEvaluationView[];
  overall: CornerSummaryView;
  odds_rows: number;
  roi_validated: boolean;
  limitation: string;
}

export interface StakingView {
  bankroll: number;
  full_kelly_fraction: number;
  recommended_fraction: number;
  recommended_stake: number;
  /** Geometric bankroll growth per bet at the recommended fraction (0.03 = +3%). */
  growth_per_bet: number;
  bets_to_double: number | null;
  horizon_bets: number;
  projected_bankroll: number;
  prob_all_win_over_horizon: number;
  expected_losses_over_horizon: number;
  /** Always 0 — staking the whole bankroll every time ends at ruin. */
  let_it_ride_bankroll: number;
  note: string;
}

export interface DailyAccaView {
  legs: AccaLegView[];
  combined_odds: number;
  combined_model_prob: number;
  combined_expected_value: number;
  target_odds: number;
  target_met: boolean;
  pool_size: number;
  model_trained: boolean;
  fixtures_scanned: number;
  candidates_scanned: number;
  markets_used: MarketType[];
  execution_mode: "paper" | "live";
  validation_model: string | null;
  validation_status: string;
  auto_tracked: boolean;
  staking: StakingView;
  note: string;
}

export interface LegCreate {
  fixture_id: string;
  home_team: string;
  away_team: string;
  kickoff_utc: string;
  league: string | null;
  provider: string;
  market_type: MarketType;
  selection: string;
  point: number | null;
  price: number;
}

export interface SlipCreate {
  name?: string | null;
  stake?: number;
  currency?: string | null;
  legs: LegCreate[];
}

export interface LegUpdate {
  leg_id: number;
  result: LegResult;
}

export interface SlipUpdate {
  name?: string | null;
  stake?: number | null;
  legs?: LegUpdate[] | null;
}

export interface LegView {
  id: number;
  fixture_id: string;
  home_team: string;
  away_team: string;
  kickoff_utc: string;
  league: string | null;
  provider: string;
  market_type: string;
  selection: string;
  point: number | null;
  price: number;
  result: LegResult;
}

export interface SlipView {
  id: number;
  name: string | null;
  stake: number;
  currency: string;
  result: SlipResult;
  created_at: string;
  settled_at: string | null;
  legs: LegView[];
  combined_odds: number;
  potential_return: number;
  potential_profit: number;
  payout: number;
  profit_loss: number;
}

export interface SlipBuilderLeg {
  fixture_id: string;
  home_team: string;
  away_team: string;
  kickoff_utc: string;
  league: string | null;
  provider: string;
  market_type: MarketType;
  selection: string;
  point: number | null;
  price: number;
  key: string;
}

export interface PersonalPoolEntry extends LegView {
  pool: "straight_win" | "corners";
  created_at: string;
  settled_at: string | null;
}

export interface PersonalPoolSummary {
  pool: "straight_win" | "corners";
  label: string;
  total: number;
  pending: number;
  won: number;
  lost: number;
  void: number;
  win_rate: number | null;
}

export interface PersonalPoolView {
  entries: PersonalPoolEntry[];
  summaries: PersonalPoolSummary[];
  note: string;
}

export interface HistoryMatch {
  id: number;
  league: string;
  season: number;
  kickoff_utc: string;
  home_team: string;
  away_team: string;
  home_goals: number;
  away_goals: number;
}

export interface TeamStatsView {
  team: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  points: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  home_record: string;
  away_record: string;
  form: string[];
}

export interface LeagueTableView {
  league: string;
  season: number;
  /** Newest first. */
  seasons: number[];
  /** Ranked by points, goal difference, goals for. */
  rows: TeamStatsView[];
}

export interface CalendarDayModel {
  candidate_count: number;
  target_met: boolean;
  combined_odds: number;
  combined_model_prob: number;
  leg_count: number;
}

export interface CalendarDay {
  date: string;
  fixture_count: number;
  /** Fixtures with live bookmaker prices; schedules alone cannot make a ticket. */
  priced_fixture_count: number;
  leagues: string[];
  slip_count: number;
  pending_count: number;
  won_count: number;
  lost_count: number;
  staked: number;
  profit_loss: number;
  model: CalendarDayModel | null;
}

export interface CalendarView {
  date_from: string;
  date_to: string;
  days: CalendarDay[];
  model_trained: boolean;
  fixture_count: number;
  profit_loss: number;
  staked: number;
  settled_slip_count: number;
}

export interface TeamMatch {
  kickoff_utc: string;
  league: string;
  opponent: string;
  venue: "H" | "A";
  result: "W" | "D" | "L";
  goals_for: number;
  goals_against: number;
  total_goals: number;
  corners_for: number | null;
  corners_against: number | null;
  total_corners: number | null;
  shots_for: number | null;
  shots_against: number | null;
  shots_on_target_for: number | null;
  shots_on_target_against: number | null;
}

export interface LineCount {
  key: string;
  label: string;
  hits: number;
  /** Matches where the stat was recorded — unrecorded corners are not misses. */
  sample: number;
}

export interface TeamAverages {
  goals_for: number | null;
  goals_against: number | null;
  total_goals: number | null;
  corners_for: number | null;
  corners_against: number | null;
  total_corners: number | null;
  shots_for: number | null;
  shots_on_target_for: number | null;
  shots_on_target_against: number | null;
}

export interface TeamForm {
  team: string;
  club_key: string | null;
  matches: TeamMatch[];
  averages: TeamAverages;
  team_lines: LineCount[];
  total_lines: LineCount[];
}

export interface HeadToHead {
  matches: TeamMatch[];
  home_wins: number;
  draws: number;
  away_wins: number;
  averages: TeamAverages;
  total_lines: LineCount[];
}

export interface TrendRow {
  key: string;
  label: string;
  home: LineCount;
  away: LineCount;
  head_to_head: LineCount;
  pooled_hits: number;
  pooled_sample: number;
  support: number;
  book_price: number | null;
  book_implied_prob: number | null;
}

export interface MatchInsights {
  fixture_id: string;
  home: TeamForm;
  away: TeamForm;
  head_to_head: HeadToHead;
  trends: TrendRow[];
  data_through: string | null;
  stale: boolean;
}

/** A betting angle graded from both sides' recent matches; computed, never generated. */
export interface Angle {
  key: string;
  label: string;
  strength: "Strong" | "Moderate" | "Weak";
  hits: number;
  sample: number;
  home_hits: number;
  home_sample: number;
  away_hits: number;
  away_sample: number;
  h2h_hits: number;
  h2h_sample: number;
  book_price: number | null;
  book_implied_prob: number | null;
}

export interface ResearchCard {
  fixture_id: string;
  league: string | null;
  kickoff_utc: string;
  home_team: string;
  away_team: string;
  /** Newest first. */
  home_form: string[];
  away_form: string[];
  home_goals_for: number | null;
  away_goals_for: number | null;
  home_avg_total_goals: number | null;
  away_avg_total_goals: number | null;
  angles: Angle[];
  has_history: boolean;
  /** False while the schedule only knows the date, not the kickoff time. */
  time_confirmed: boolean;
  stale: boolean;
  priced: boolean;
}

export interface ResearchDay {
  date_from: string;
  date_to: string;
  leagues: string[];
  cards: ResearchCard[];
}

export interface MatchReadView {
  status: "ok" | "no_key" | "no_history" | "error";
  angles: Angle[];
  angle_key: string | null;
  headline: string | null;
  summary: string | null;
  match_read: string | null;
  model: string | null;
  generated_at: string | null;
  message: string | null;
}
