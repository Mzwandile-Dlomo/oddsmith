"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  FlaskConical,
  LayoutGrid,
  ListChecks,
  Sparkles,
  Sun,
  Trophy,
} from "lucide-react";
import { fetchSlips } from "@/lib/api";
import { formatSignedCurrency } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  hint: string;
}

/** Ordered by the daily routine: check today, plan ahead, then review. */
const PRIMARY: NavItem[] = [
  { href: "/today", label: "Today", icon: Sun, hint: "Today's slip and card" },
  { href: "/calendar", label: "Calendar", icon: CalendarDays, hint: "Plan and review by day" },
  { href: "/slips", label: "Slips", icon: ListChecks, hint: "Open bets and settling" },
  { href: "/results", label: "Results", icon: Trophy, hint: "Settled outcomes and history" },
];

const SECONDARY: NavItem[] = [
  { href: "/build", label: "Build", icon: LayoutGrid, hint: "Manual bet builder" },
  { href: "/generate", label: "Value", icon: Sparkles, hint: "Positive-EV selections" },
  { href: "/model", label: "Model", icon: FlaskConical, hint: "Evidence and validation" },
];

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      title={item.hint}
      aria-current={active ? "page" : undefined}
      className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-150 ${
        active
          ? "bg-[#EEE9FF] text-[#6C47FF]"
          : "text-[#6B7280] hover:bg-[#F3F4F6] hover:text-[#111827]"
      }`}
    >
      <Icon
        size={16}
        className={active ? "text-[#6C47FF]" : "text-[#9CA3AF] group-hover:text-[#6B7280]"}
      />
      {item.label}
    </Link>
  );
}

/** Running bankroll position, derived from settled slips. */
function BankrollSummary() {
  const { data: slips } = useQuery({ queryKey: ["slips"], queryFn: fetchSlips });

  if (!slips) return null;

  const settled = slips.filter((s) => s.result !== "pending");
  const pending = slips.filter((s) => s.result === "pending");
  const pnl = settled.reduce((acc, s) => acc + s.profit_loss, 0);
  const atRisk = pending.reduce((acc, s) => acc + s.stake, 0);
  const currency = slips[0]?.currency ?? "USD";

  return (
    <div className="border-t border-[#E5E7EB] px-3 py-4">
      <p className="px-3 text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
        Net profit / loss
      </p>
      <p
        className={`mt-1 px-3 text-lg font-semibold tabular-nums tracking-tight ${
          pnl > 0 ? "text-[#059669]" : pnl < 0 ? "text-[#DC2626]" : "text-[#111827]"
        }`}
      >
        {settled.length === 0 ? "—" : formatSignedCurrency(pnl, currency)}
      </p>
      <p className="mt-1 px-3 text-xs text-[#6B7280]">
        {settled.length} settled
        {pending.length > 0 && (
          <>
            {" · "}
            <span className="text-[#D97706]">
              {currency} {atRisk.toFixed(2)} at risk
            </span>
          </>
        )}
      </p>
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-[#E5E7EB] bg-white lg:flex">
      <div className="flex h-16 shrink-0 items-center gap-2.5 border-b border-[#E5E7EB] px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#6C47FF]">
          <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true" fill="none">
            <path
              d="M12 3C7.03 3 3 7.03 3 12s4.03 9 9 9 9-4.03 9-9-4.03-9-9-9z"
              fill="white"
              opacity="0.3"
            />
            <circle cx="12" cy="12" r="5" fill="white" />
            <path
              d="M9.5 12l1.5 1.5 3.5-3.5"
              stroke="#6C47FF"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <span className="text-[15px] font-semibold tracking-tight text-[#111827]">
          Oddsmith
        </span>
      </div>

      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
        {PRIMARY.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(pathname, item.href)} />
        ))}

        <p className="mt-5 mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
          Tools
        </p>
        {SECONDARY.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(pathname, item.href)} />
        ))}
      </nav>

      <BankrollSummary />
    </aside>
  );
}

/** Horizontal nav for viewports too narrow for the sidebar. */
export function MobileNav() {
  const pathname = usePathname();
  const items = [...PRIMARY, ...SECONDARY];

  return (
    <nav className="flex items-center gap-1 overflow-x-auto px-4 pb-2 lg:hidden">
      {items.map((item) => {
        const active = isActive(pathname, item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              active
                ? "bg-[#EEE9FF] text-[#6C47FF]"
                : "text-[#6B7280] hover:bg-[#F3F4F6]"
            }`}
          >
            <Icon size={15} />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
