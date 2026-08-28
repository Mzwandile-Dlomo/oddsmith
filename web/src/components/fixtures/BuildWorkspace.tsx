"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { FixtureBrowser, type Timeframe } from "@/components/fixtures/FixtureBrowser";
import { SlipPanel } from "@/components/slip/SlipPanel";

export function BuildWorkspace() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [timeframe, setTimeframe] = useState<Timeframe>("3days");

  function handleSlipSaved() {
    queryClient.invalidateQueries({ queryKey: ["slips"] });
    router.push("/slips");
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_340px]">
      <FixtureBrowser timeframe={timeframe} onTimeframeChange={setTimeframe} />
      <div className="lg:sticky lg:top-6 lg:self-start">
        <div className="overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-[0_4px_16px_rgba(0,0,0,0.08)]">
          <SlipPanel onSlipSaved={handleSlipSaved} />
        </div>
      </div>
    </div>
  );
}
