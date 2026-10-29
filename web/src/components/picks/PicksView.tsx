"use client";

import Link from "next/link";
import { Flame, Pin, Sparkles, Target } from "lucide-react";
import { todayISO } from "@/lib/utils";
import { DailyAcca } from "@/components/generator/DailyAcca";
import { OddsGenerator } from "@/components/generator/OddsGenerator";
import { StrongSlip } from "@/components/generator/StrongSlip";
import { PersonalPool } from "@/components/pool/PersonalPool";
import type { PickTab } from "./tabs";

const TABS: { value: PickTab; label: string; icon: React.ElementType; hint: string }[] = [
  { value: "daily", label: "Daily slip", icon: Target, hint: "The likeliest slip that clears your target price" },
  { value: "strong", label: "Strong slip", icon: Flame, hint: "Stacked from the most consistent form lines over the next few days" },
  { value: "value", label: "Value acca", icon: Sparkles, hint: "Positive-EV legs across the weekend" },
  { value: "pool", label: "Pool", icon: Pin, hint: "Your own favoured selections, tracked separately" },
];

/** Every way of getting selections lives here; Matches is for browsing them. */
export function PicksView({ tab }: { tab: PickTab }) {
  const active = TABS.find((t) => t.value === tab) ?? TABS[0];

  return (
    <div className="flex flex-col gap-5">
      <nav
        aria-label="Pick type"
        className="scroll-x inline-flex max-w-full items-center gap-1 self-start rounded-xl border border-border bg-surface p-1 shadow-card"
      >
        {TABS.map((t) => {
          const Icon = t.icon;
          const current = t.value === active.value;
          return (
            <Link
              key={t.value}
              href={t.value === "daily" ? "/picks" : `/picks?tab=${t.value}`}
              aria-current={current ? "page" : undefined}
              className={`flex min-h-[44px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-3 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[32px] ${
                current ? "bg-accent-light text-accent" : "text-muted hover:bg-hairline hover:text-ink"
              }`}
            >
              <Icon size={14} />
              {t.label}
            </Link>
          );
        })}
      </nav>
      <p className="-mt-2 text-sm text-muted">{active.hint}.</p>

      {active.value === "daily" && <DailyAcca date={todayISO()} autoLoad autoTrack />}
      {active.value === "strong" && <StrongSlip />}
      {active.value === "value" && <OddsGenerator />}
      {active.value === "pool" && <PersonalPool />}
    </div>
  );
}
