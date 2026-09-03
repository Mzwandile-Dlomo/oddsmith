"use client";

import { useMemo } from "react";
import type { Fixture, Market, MarketType, ModelMarket, ModelOutcome, Outcome } from "@/lib/types";
import { formatOdds, marketLabel, outcomeLabel } from "@/lib/utils";
import { useSlipStore } from "@/store/slip-store";

interface MarketPickerProps {
  fixture: Fixture;
}

interface BestOutcome extends Outcome {
  bestPrice: number;
}

interface DeduplicatedMarket {
  type: MarketType;
  outcomes: BestOutcome[];
}

function deduplicateMarkets(markets: Market[]): DeduplicatedMarket[] {
  const byType = new Map<MarketType, Map<string, number>>();

  for (const market of markets) {
    if (!byType.has(market.type)) {
      byType.set(market.type, new Map());
    }
    const outcomeMap = byType.get(market.type)!;
    for (const outcome of market.outcomes) {
      const existing = outcomeMap.get(outcome.name) ?? 0;
      if (outcome.price > existing) {
        outcomeMap.set(outcome.name, outcome.price);
      }
    }
  }

  const result: DeduplicatedMarket[] = [];
  byType.forEach((outcomeMap, type) => {
    const outcomes: BestOutcome[] = [];
    const referenceMarket = markets.find((m) => m.type === type);
    if (!referenceMarket) return;

    referenceMarket.outcomes.forEach((o) => {
      const bestPrice = outcomeMap.get(o.name) ?? o.price;
      outcomes.push({ ...o, price: bestPrice, bestPrice });
    });

    result.push({ type, outcomes });
  });

  return result;
}

function ValueBadge({ edge }: { edge: number }) {
  const pct = Math.round(edge * 100);
  return (
    <span className="inline-flex items-center rounded-full bg-accent-light px-1.5 py-0.5 text-[9px] font-semibold text-accent leading-none">
      Value +{pct}%
    </span>
  );
}

function ModelOddsRow({ outcome }: { outcome: ModelOutcome }) {
  return (
    <span className="flex items-center gap-1 text-[10px] text-faint">
      <span className="font-medium text-accent">{formatOdds(outcome.model_odds)}</span>
      <span>model</span>
      {outcome.is_value && outcome.edge !== null && <ValueBadge edge={outcome.edge} />}
    </span>
  );
}

interface EnrichedOutcome extends BestOutcome {
  modelOutcome: ModelOutcome | null;
}

interface EnrichedMarket {
  type: MarketType;
  outcomes: EnrichedOutcome[];
  isModelOnly: boolean;
}

function buildEnrichedMarkets(
  deduped: DeduplicatedMarket[],
  modelMarkets: ModelMarket[]
): EnrichedMarket[] {
  const modelByType = new Map<MarketType, ModelMarket>();
  for (const mm of modelMarkets) {
    modelByType.set(mm.type, mm);
  }

  const result: EnrichedMarket[] = deduped.map((dm) => {
    const modelMarket = modelByType.get(dm.type);
    const outcomes: EnrichedOutcome[] = dm.outcomes.map((o) => {
      const modelOutcome = modelMarket?.outcomes.find((mo) => mo.name === o.name) ?? null;
      return { ...o, modelOutcome };
    });
    return { type: dm.type, outcomes, isModelOnly: false };
  });

  for (const mm of modelMarkets) {
    const alreadyPresent = result.some((r) => r.type === mm.type);
    if (!alreadyPresent) {
      const outcomes: EnrichedOutcome[] = mm.outcomes.map((mo) => ({
        name: mo.name,
        price: 0,
        bestPrice: 0,
        point: mo.point,
        modelOutcome: mo,
      }));
      result.push({ type: mm.type, outcomes, isModelOnly: true });
    }
  }

  const order: MarketType[] = ["match_winner", "over_under", "btts", "double_chance"];
  result.sort((a, b) => {
    const ai = order.indexOf(a.type);
    const bi = order.indexOf(b.type);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  return result;
}

export function MarketPicker({ fixture }: MarketPickerProps) {
  const { addLeg, getSelection } = useSlipStore();

  const deduped = useMemo(
    () => deduplicateMarkets(fixture.markets),
    [fixture.markets]
  );

  const enriched = useMemo(
    () => buildEnrichedMarkets(deduped, fixture.model_markets ?? []),
    [deduped, fixture.model_markets]
  );

  if (enriched.length === 0) {
    return (
      <p className="text-xs italic text-faint">No markets available</p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {enriched.map((market) => {
        const activeSelection = getSelection(fixture.id, market.type);
        return (
          <div key={market.type}>
            <div className="mb-2.5 flex items-center gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">
                {marketLabel(market.type)}
              </p>
              {market.isModelOnly && (
                <span className="rounded-full bg-hairline px-1.5 py-0.5 text-[9px] font-medium text-faint uppercase tracking-wide">
                  Model only
                </span>
              )}
            </div>
            {/*
              `auto-fill` packs as many ~84px tracks as fit, so a 1X2 market
              still reads as a 3-up row on a 375px phone while the buttons stay
              a sane size on a wide monitor instead of stretching to thirds.
            */}
            <div
              className="grid gap-2"
              style={{
                gridTemplateColumns: "repeat(auto-fill, minmax(min(84px, 100%), 1fr))",
              }}
            >
              {market.outcomes.map((outcome) => {
                const label = outcomeLabel(
                  market.type,
                  outcome.name,
                  outcome.point,
                  fixture.home_team,
                  fixture.away_team
                );
                const isActive = activeSelection === outcome.name;

                if (market.isModelOnly) {
                  return (
                    <div
                      key={outcome.name}
                      className="flex min-h-[64px] min-w-0 flex-col items-start rounded-xl border border-dashed border-outline bg-canvas px-2.5 py-2.5 sm:px-3"
                    >
                      <span className="text-xs font-medium leading-tight text-muted">
                        {label}
                      </span>
                      {outcome.modelOutcome && (
                        <div className="mt-1 flex flex-col gap-0.5">
                          <span className="text-[13px] font-bold tabular-nums text-accent">
                            {formatOdds(outcome.modelOutcome.model_odds)}
                          </span>
                          <span className="text-[9px] text-faint">model odds</span>
                          {outcome.modelOutcome.is_value && outcome.modelOutcome.edge !== null && (
                            <ValueBadge edge={outcome.modelOutcome.edge} />
                          )}
                        </div>
                      )}
                    </div>
                  );
                }

                return (
                  <button
                    key={outcome.name}
                    onClick={() =>
                      addLeg({
                        fixture_id: fixture.id,
                        home_team: fixture.home_team,
                        away_team: fixture.away_team,
                        kickoff_utc: fixture.kickoff_utc,
                        league: fixture.league,
                        provider: fixture.provider,
                        market_type: market.type,
                        selection: outcome.name,
                        point: outcome.point,
                        price: outcome.bestPrice,
                      })
                    }
                    className={`group flex min-h-[64px] min-w-0 flex-col items-start rounded-xl border px-2.5 py-2.5 transition-all duration-150 sm:px-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
                      isActive
                        ? "border-accent/40 bg-accent-light ring-1 ring-accent/20 shadow-glow"
                        : "border-border bg-surface hover:border-outline hover:bg-subtle hover:shadow-raised"
                    }`}
                  >
                    <span
                      className={`text-xs font-medium leading-tight ${
                        isActive ? "text-accent" : "text-muted"
                      }`}
                    >
                      {label}
                    </span>
                    <span
                      className={`mt-0.5 text-[13px] font-bold tabular-nums ${
                        isActive ? "text-accent" : "text-ink"
                      }`}
                    >
                      {formatOdds(outcome.bestPrice)}
                    </span>
                    {outcome.modelOutcome && (
                      <div className="mt-1">
                        <ModelOddsRow outcome={outcome.modelOutcome} />
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
