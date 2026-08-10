"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import type { MarketType, SlipBuilderLeg } from "@/lib/types";
import { combinedOdds } from "@/lib/utils";

interface SlipStore {
  legs: SlipBuilderLeg[];
  addLeg: (leg: Omit<SlipBuilderLeg, "key">) => void;
  removeLeg: (key: string) => void;
  clearLegs: () => void;
  hasSelection: (fixtureId: string, marketType: MarketType) => boolean;
  getSelection: (fixtureId: string, marketType: MarketType) => string | null;
  computedOdds: number;
}

const SlipContext = createContext<SlipStore | null>(null);

function makeKey(fixtureId: string, marketType: MarketType): string {
  return `${fixtureId}::${marketType}`;
}

export function SlipStoreProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [legs, setLegs] = useState<SlipBuilderLeg[]>([]);

  const addLeg = useCallback((leg: Omit<SlipBuilderLeg, "key">) => {
    const key = makeKey(leg.fixture_id, leg.market_type);
    setLegs((prev) => {
      const withoutExisting = prev.filter((l) => l.key !== key);
      return [...withoutExisting, { ...leg, key }];
    });
  }, []);

  const removeLeg = useCallback((key: string) => {
    setLegs((prev) => prev.filter((l) => l.key !== key));
  }, []);

  const clearLegs = useCallback(() => setLegs([]), []);

  const hasSelection = useCallback(
    (fixtureId: string, marketType: MarketType) => {
      const key = makeKey(fixtureId, marketType);
      return legs.some((l) => l.key === key);
    },
    [legs]
  );

  const getSelection = useCallback(
    (fixtureId: string, marketType: MarketType) => {
      const key = makeKey(fixtureId, marketType);
      return legs.find((l) => l.key === key)?.selection ?? null;
    },
    [legs]
  );

  const computedOdds = useMemo(
    () => combinedOdds(legs.map((l) => l.price)),
    [legs]
  );

  const value = useMemo(
    () => ({
      legs,
      addLeg,
      removeLeg,
      clearLegs,
      hasSelection,
      getSelection,
      computedOdds,
    }),
    [legs, addLeg, removeLeg, clearLegs, hasSelection, getSelection, computedOdds]
  );

  return <SlipContext.Provider value={value}>{children}</SlipContext.Provider>;
}

export function useSlipStore(): SlipStore {
  const ctx = useContext(SlipContext);
  if (!ctx) throw new Error("useSlipStore must be used within SlipStoreProvider");
  return ctx;
}
