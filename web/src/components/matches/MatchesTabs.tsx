"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarDays, List } from "lucide-react";

const TABS = [
  { href: "/matches", label: "List", icon: List },
  { href: "/matches/calendar", label: "Calendar", icon: CalendarDays },
];

/** Two views of the same fixtures: the next few days as a list, or by month. */
export function MatchesTabs() {
  const pathname = usePathname();
  const calendar = pathname.startsWith("/matches/calendar");

  return (
    <div className="inline-flex items-center gap-1 rounded-xl border border-border bg-surface p-1 shadow-card">
      {TABS.map((tab) => {
        const active = tab.href === "/matches/calendar" ? calendar : !calendar;
        const Icon = tab.icon;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={`flex min-h-[44px] items-center gap-1.5 rounded-lg px-3 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:min-h-[32px] ${
              active ? "bg-accent-light text-accent" : "text-muted hover:bg-hairline hover:text-ink"
            }`}
          >
            <Icon size={14} />
            {tab.label}
          </Link>
        );
      })}
    </div>
  );
}
