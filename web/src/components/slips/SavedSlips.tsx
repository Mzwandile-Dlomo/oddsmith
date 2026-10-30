"use client";

import { useState, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSlips } from "@/lib/api";
import type { SlipView } from "@/lib/types";
import { formatCurrency, formatOdds, resultBadgeClass } from "@/lib/utils";
import { SpinnerOverlay } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { SlipCard } from "./SlipCard";
import { BookOpen } from "lucide-react";

const DESKTOP = "(min-width: 1024px)";

/** Tailwind's `lg`. False on the server, so the first paint is the phone layout. */
function useIsDesktop(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const query = window.matchMedia(DESKTOP);
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    },
    () => window.matchMedia(DESKTOP).matches,
    () => false
  );
}

function SlipRow({
  slip,
  selected,
  onSelect,
}: {
  slip: SlipView;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 ${
        selected
          ? "border-accent/40 bg-accent-light"
          : "border-transparent hover:border-border hover:bg-subtle"
      }`}
    >
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">
        {slip.name ?? `Slip #${slip.id}`}
      </span>
      <span className="shrink-0 text-xs font-semibold tabular-nums text-accent">
        {formatOdds(slip.combined_odds)}
      </span>
      {slip.result !== "pending" && (
        <span
          className={`hidden w-16 shrink-0 text-right text-xs font-semibold tabular-nums xl:inline ${
            slip.profit_loss >= 0 ? "text-success" : "text-danger"
          }`}
        >
          {slip.profit_loss >= 0 ? "+" : ""}
          {formatCurrency(slip.profit_loss, slip.currency)}
        </span>
      )}
      <Badge className={`shrink-0 ${resultBadgeClass(slip.result)}`}>{slip.result}</Badge>
    </button>
  );
}

export function SavedSlips() {
  const isDesktop = useIsDesktop();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data: slips, isLoading, isError, error } = useQuery({
    queryKey: ["slips"],
    queryFn: fetchSlips,
  });

  if (isLoading) return <SpinnerOverlay label="Loading saved slips…" />;

  if (isError) {
    return (
      <div className="rounded-xl border border-danger-line bg-danger-faint px-4 py-3 text-sm text-danger">
        {error instanceof Error ? error.message : "Failed to load slips."}
      </div>
    );
  }

  if (!slips || slips.length === 0) {
    return (
      <EmptyState
        icon={<BookOpen size={22} />}
        title="No saved slips yet"
        description="Build a bet slip from the fixtures view and save it — it'll appear here."
      />
    );
  }

  // A phone has no room for a second column, so it keeps the expandable list.
  if (!isDesktop) {
    return (
      <div className="flex flex-col gap-3">
        {slips.map((slip) => (
          <SlipCard key={slip.id} slip={slip} />
        ))}
      </div>
    );
  }

  // Newest first from the API, so the default selection is the latest slip.
  const selected = slips.find((s) => s.id === selectedId) ?? slips[0];

  return (
    <div className="grid grid-cols-[minmax(0,22rem)_minmax(0,1fr)] items-start gap-5 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      <nav
        aria-label="Saved slips"
        className="flex max-h-[calc(100vh-8rem)] flex-col gap-1 overflow-y-auto rounded-xl border border-border bg-surface p-2 shadow-card"
      >
        {slips.map((slip) => (
          <SlipRow
            key={slip.id}
            slip={slip}
            selected={slip.id === selected.id}
            onSelect={() => setSelectedId(slip.id)}
          />
        ))}
      </nav>
      {/* Keyed so unsaved leg choices on one slip never carry over to the next. */}
      <div className="sticky top-6">
        <SlipCard key={selected.id} slip={selected} alwaysOpen />
      </div>
    </div>
  );
}
