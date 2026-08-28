"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FixtureBrowser, type Timeframe } from "@/components/fixtures/FixtureBrowser";
import { SlipPanel } from "@/components/slip/SlipPanel";
import { SavedSlips } from "@/components/slips/SavedSlips";
import { OddsGenerator } from "@/components/generator/OddsGenerator";
import { DailyAcca } from "@/components/generator/DailyAcca";
import { ResultsView } from "@/components/history/ResultsView";
import { ModelLab } from "@/components/model/ModelLab";

type Tab = "build" | "slips" | "daily" | "generate" | "model" | "results";

const VALID_TABS: Tab[] = ["build", "slips", "daily", "generate", "model", "results"];
const TAB_COPY: Record<Tab, { title: string; description: string }> = {
  build: {
    title: "Bet Builder",
    description: "Browse fixtures, compare prices, and build a manual slip.",
  },
  slips: {
    title: "My Slips",
    description: "Track stakes, settle selections, and measure actual profit and loss.",
  },
  daily: {
    title: "Daily Target",
    description: "Build the highest-confidence value slip that clears your target odds.",
  },
  generate: {
    title: "Value Generator",
    description: "Find positive-EV selections across the available fixture window.",
  },
  model: {
    title: "Model Lab",
    description: "See the evidence, coverage, limitations, and next validation gates.",
  },
  results: {
    title: "Results Explorer",
    description: "Inspect historical matches, team form, and the model's source data.",
  },
};
const VALID_TIMEFRAMES: Timeframe[] = ["today", "3days", "7days"];
const LS_TAB_KEY = "oddsmith_tab";
const LS_WINDOW_KEY = "oddsmith_window";

function parseTab(v: string | null): Tab | null {
  return VALID_TABS.includes(v as Tab) ? (v as Tab) : null;
}

function parseTimeframe(v: string | null): Timeframe | null {
  return VALID_TIMEFRAMES.includes(v as Timeframe) ? (v as Timeframe) : null;
}

function readLS(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLS(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

function getStoredTab(): Tab {
  const params = new URLSearchParams(window.location.search);
  return parseTab(params.get("tab")) ?? parseTab(readLS(LS_TAB_KEY)) ?? "build";
}

function getStoredTimeframe(): Timeframe {
  const params = new URLSearchParams(window.location.search);
  return parseTimeframe(params.get("window")) ?? parseTimeframe(readLS(LS_WINDOW_KEY)) ?? "3days";
}

export default function Home() {
  const queryClient = useQueryClient();

  const [tab, setTab] = useState<Tab>("build");
  const [timeframe, setTimeframe] = useState<Timeframe>("3days");

  useEffect(() => {
    // Client-only: restore persisted tab/timeframe after hydration, then keep
    // the URL in sync. Runs once on mount (server render used the defaults).
    const storedTab = getStoredTab();
    const storedTimeframe = getStoredTimeframe();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTab(storedTab);
    setTimeframe(storedTimeframe);
    writeLS(LS_TAB_KEY, storedTab);
    writeLS(LS_WINDOW_KEY, storedTimeframe);
    const params = new URLSearchParams(window.location.search);
    params.set("tab", storedTab);
    params.set("window", storedTimeframe);
    window.history.replaceState(null, "", `?${params.toString()}`);
  }, []);

  function updateTab(next: Tab) {
    setTab(next);
    writeLS(LS_TAB_KEY, next);
    const params = new URLSearchParams(window.location.search);
    params.set("tab", next);
    window.history.replaceState(null, "", `?${params.toString()}`);
  }

  function updateTimeframe(next: Timeframe) {
    setTimeframe(next);
    writeLS(LS_WINDOW_KEY, next);
    const params = new URLSearchParams(window.location.search);
    params.set("window", next);
    window.history.replaceState(null, "", `?${params.toString()}`);
  }

  const handleSlipSaved = () => {
    queryClient.invalidateQueries({ queryKey: ["slips"] });
    updateTab("slips");
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight text-[#111827]">
          {TAB_COPY[tab].title}
        </h1>
        <p className="mt-1 text-sm text-[#6B7280]">
          {TAB_COPY[tab].description}
        </p>
      </div>

      <div className="mb-6 flex items-center gap-0 overflow-x-auto border-b border-[#E5E7EB]">
        <TabButton active={tab === "build"} onClick={() => updateTab("build")}>
          Build
        </TabButton>
        <TabButton active={tab === "slips"} onClick={() => updateTab("slips")}>
          My Slips
        </TabButton>
        <TabButton active={tab === "daily"} onClick={() => updateTab("daily")}>
          Daily Slip
        </TabButton>
        <TabButton active={tab === "generate"} onClick={() => updateTab("generate")}>
          Odds Generator
        </TabButton>
        <TabButton active={tab === "model"} onClick={() => updateTab("model")}>
          Model Lab
        </TabButton>
        <TabButton active={tab === "results"} onClick={() => updateTab("results")}>
          Results
        </TabButton>
      </div>

      {tab === "build" ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_340px]">
          <FixtureBrowser timeframe={timeframe} onTimeframeChange={updateTimeframe} />
          <div className="lg:sticky lg:top-[88px] lg:self-start">
            <div className="overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-[0_4px_16px_rgba(0,0,0,0.08)]">
              <SlipPanel onSlipSaved={handleSlipSaved} />
            </div>
          </div>
        </div>
      ) : tab === "slips" ? (
        <SavedSlips />
      ) : tab === "daily" ? (
        <DailyAcca />
      ) : tab === "generate" ? (
        <OddsGenerator />
      ) : tab === "model" ? (
        <ModelLab />
      ) : (
        <ResultsView />
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`-mb-px shrink-0 border-b-2 px-5 py-3 text-sm font-medium transition-colors duration-150 ${
        active
          ? "border-[#6C47FF] text-[#6C47FF]"
          : "border-transparent text-[#6B7280] hover:text-[#111827]"
      }`}
    >
      {children}
    </button>
  );
}
