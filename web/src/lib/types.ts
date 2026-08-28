export type MarketType = "match_winner" | "btts" | "over_under" | "double_chance";
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
  coverage: DataCoverageView[];
  league_coverage: LeagueCoverageView[];
  markets: MarketReadinessView[];
  next_priorities: string[];
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
