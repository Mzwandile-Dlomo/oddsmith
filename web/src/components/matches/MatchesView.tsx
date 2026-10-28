"use client";

import { useState } from "react";
import { FixtureBrowser, type Timeframe } from "@/components/fixtures/FixtureBrowser";
import { SlipDock } from "@/components/slip/SlipDock";

export function MatchesView() {
  const [timeframe, setTimeframe] = useState<Timeframe>("3days");

  return (
    <SlipDock>
      <FixtureBrowser timeframe={timeframe} onTimeframeChange={setTimeframe} />
    </SlipDock>
  );
}
