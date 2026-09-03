"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronUp, Receipt, X } from "lucide-react";
import { FixtureBrowser, type Timeframe } from "@/components/fixtures/FixtureBrowser";
import { SlipPanel } from "@/components/slip/SlipPanel";
import { useSlipStore } from "@/store/slip-store";
import { formatOdds } from "@/lib/utils";

export function BuildWorkspace() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [timeframe, setTimeframe] = useState<Timeframe>("3days");
  const [sheetOpen, setSheetOpen] = useState(false);
  const { legs, computedOdds } = useSlipStore();

  function handleSlipSaved() {
    setSheetOpen(false);
    queryClient.invalidateQueries({ queryKey: ["slips"] });
    router.push("/slips");
  }

  // An empty slip has nothing to show, so the sheet is derived rather than
  // closed after the fact in an effect.
  const showSheet = sheetOpen && legs.length > 0;

  // An open sheet covers the page; the list behind it must not scroll, and
  // Escape should dismiss it.
  useEffect(() => {
    if (!showSheet) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSheetOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [showSheet]);

  return (
    <>
      {/*
        Two columns from `lg` where the slip can sit beside the fixtures. Below
        that the panel is a bottom sheet rather than a block stacked underneath
        a long fixture list, where a selection would scroll out of sight.
      */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_380px]">
        <FixtureBrowser timeframe={timeframe} onTimeframeChange={setTimeframe} />

        <div className="hidden lg:sticky lg:top-6 lg:block lg:max-h-[calc(100dvh-3rem)] lg:self-start lg:overflow-y-auto lg:overscroll-contain">
          <div className="overflow-hidden rounded-2xl border border-border bg-surface shadow-panel">
            <SlipPanel onSlipSaved={handleSlipSaved} />
          </div>
        </div>
      </div>

      {/* Mobile: a summary bar docked above the tab bar, opening the full panel. */}
      {legs.length > 0 && !showSheet && (
        <button
          onClick={() => setSheetOpen(true)}
          aria-haspopup="dialog"
          className="fixed inset-x-3 bottom-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom,0px)+0.5rem)] z-40 flex min-h-[52px] items-center gap-3 rounded-2xl bg-accent px-4 text-white shadow-elevated transition-transform active:scale-[0.99] lg:hidden"
        >
          <Receipt size={17} className="shrink-0" />
          <span className="flex min-w-0 flex-col items-start leading-tight">
            <span className="text-sm font-semibold">
              {legs.length} {legs.length === 1 ? "selection" : "selections"}
            </span>
            <span className="text-[11px] text-white/75">Tap to review and save</span>
          </span>
          <span className="ml-auto flex shrink-0 items-center gap-1.5">
            <span className="text-base font-bold tabular-nums">
              {formatOdds(computedOdds)}
            </span>
            <ChevronUp size={16} />
          </span>
        </button>
      )}

      {showSheet && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            aria-label="Close bet slip"
            onClick={() => setSheetOpen(false)}
            className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Bet slip"
            className="absolute inset-x-0 bottom-0 flex max-h-[88dvh] flex-col rounded-t-2xl border-t border-border bg-surface shadow-sheet"
          >
            <div className="shrink-0 border-b border-hairline">
              {/* Grab handle, the conventional "this sheet drags down" cue. */}
              <span
                aria-hidden
                className="mx-auto mt-1.5 block h-1 w-9 rounded-full bg-outline"
              />
              <div className="flex items-center justify-between px-4 pb-2 pt-1">
                <span className="text-sm font-semibold text-ink">Bet slip</span>
                <button
                  onClick={() => setSheetOpen(false)}
                  aria-label="Close bet slip"
                  className="-mr-2 flex h-11 w-11 items-center justify-center rounded-lg text-faint transition-colors hover:bg-hairline hover:text-ink"
                >
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-safe">
              <SlipPanel onSlipSaved={handleSlipSaved} hideHeader />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
