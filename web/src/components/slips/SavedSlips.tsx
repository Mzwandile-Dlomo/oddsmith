"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchSlips } from "@/lib/api";
import { SpinnerOverlay } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { SlipCard } from "./SlipCard";
import { BookOpen } from "lucide-react";

export function SavedSlips() {
  const { data: slips, isLoading, isError, error } = useQuery({
    queryKey: ["slips"],
    queryFn: fetchSlips,
  });

  if (isLoading) return <SpinnerOverlay label="Loading saved slips…" />;

  if (isError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
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

  return (
    <div className="flex flex-col gap-3">
      {slips.map((slip) => (
        <SlipCard key={slip.id} slip={slip} />
      ))}
    </div>
  );
}
