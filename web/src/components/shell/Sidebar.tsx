"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  CalendarDays,
  FlaskConical,
  LayoutDashboard,
  ListChecks,
  Menu,
  Search,
  Sparkles,
  Trophy,
  Users,
  X,
} from "lucide-react";
import { fetchSlips } from "@/lib/api";
import { formatSignedCurrency } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  hint: string;
}

/**
 * One flat list of places, not a list of tasks: each entry is a thing you
 * browse, and detail pages (a match, a team) hang off the list that leads to them.
 */
const NAV: NavItem[] = [
  { href: "/", label: "Matches", icon: CalendarDays, hint: "Each day's matches with form, trends and a written read" },
  { href: "/overview", label: "Overview", icon: LayoutDashboard, hint: "Your numbers at a glance" },
  { href: "/picks", label: "Picks", icon: Sparkles, hint: "Daily slip, value acca and pool" },
  { href: "/slips", label: "Slips", icon: ListChecks, hint: "Open bets and settling" },
  { href: "/analytics", label: "Analytics", icon: BarChart3, hint: "Profit, hit rate and paper tracking" },
  { href: "/leagues", label: "Leagues", icon: Trophy, hint: "Tables and results" },
  { href: "/teams", label: "Teams", icon: Users, hint: "Form, record and results" },
  { href: "/model", label: "Model", icon: FlaskConical, hint: "Evidence and validation" },
];

function isActive(pathname: string, href: string): boolean {
  // Match pages and the calendar hang off the home feed.
  if (href === "/") return pathname === "/" || pathname.startsWith("/matches");
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Wordmark({ size = "md" }: { size?: "sm" | "md" }) {
  const box = size === "sm" ? "h-7 w-7" : "h-8 w-8";
  const glyph = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";
  return (
    <span className="flex items-center gap-2.5">
      <span className={`flex ${box} items-center justify-center rounded-md border border-accent/30 bg-accent shadow-[0_0_22px_rgba(216,255,69,0.18)]`}>
        <svg viewBox="0 0 24 24" className={glyph} aria-hidden="true" fill="none">
          <path
            d="M12 3C7.03 3 3 7.03 3 12s4.03 9 9 9 9-4.03 9-9-4.03-9-9-9z"
            fill="white"
            opacity="0.3"
          />
          <circle cx="12" cy="12" r="5" fill="white" />
          <path
            d="M9.5 12l1.5 1.5 3.5-3.5"
            stroke="#18210f"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-ink">Oddsmith<span className="text-accent">/</span></span>
    </span>
  );
}

/** Bankroll figures derived from settled slips, shared by every shell surface. */
export function useBankroll() {
  const { data: slips } = useQuery({ queryKey: ["slips"], queryFn: fetchSlips });
  if (!slips) return null;

  const settled = slips.filter((s) => s.result !== "pending");
  const pending = slips.filter((s) => s.result === "pending");
  return {
    pnl: settled.reduce((acc, s) => acc + s.profit_loss, 0),
    atRisk: pending.reduce((acc, s) => acc + s.stake, 0),
    settledCount: settled.length,
    pendingCount: pending.length,
    currency: slips[0]?.currency ?? "ZAR",
  };
}

function pnlTone(pnl: number): string {
  return pnl > 0 ? "text-success" : pnl < 0 ? "text-danger" : "text-ink";
}

function NavList({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
      {NAV.map((item) => {
        const active = isActive(pathname, item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            title={item.hint}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`group flex min-h-[44px] items-center gap-3 rounded-xl border px-3 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 lg:min-h-[40px] ${
              active
                ? "border-accent/20 bg-accent-light text-accent"
                : "border-transparent text-muted hover:bg-hairline hover:text-ink"
            }`}
          >
            <Icon
              size={17}
              className={`shrink-0 ${active ? "text-accent" : "text-faint group-hover:text-muted"}`}
            />
            {item.label}
            {active && <span aria-hidden className="ml-auto h-1.5 w-1.5 rounded-full bg-accent" />}
          </Link>
        );
      })}
    </nav>
  );
}

/** Running bankroll position, derived from settled slips. */
function BankrollSummary() {
  const bankroll = useBankroll();
  if (!bankroll) return null;

  return (
    <div className="border-t border-border px-6 py-4">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-faint">
        Net profit / loss
      </p>
      <p
        className={`mt-1 text-lg font-semibold tabular-nums tracking-tight ${pnlTone(bankroll.pnl)}`}
      >
        {bankroll.settledCount === 0
          ? "—"
          : formatSignedCurrency(bankroll.pnl, bankroll.currency)}
      </p>
      <p className="mt-1 text-xs text-muted">
        {bankroll.settledCount} settled
        {bankroll.pendingCount > 0 && (
          <>
            {" · "}
            <span className="text-warn">
              {bankroll.currency} {bankroll.atRisk.toFixed(2)} at risk
            </span>
          </>
        )}
      </p>
    </div>
  );
}

function SidebarBody({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <>
      <NavList pathname={pathname} onNavigate={onNavigate} />
      <BankrollSummary />
    </>
  );
}

/** Team search: the one search that has a page to land on. */
function TeamSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  return (
    <form
      role="search"
      className="relative min-w-0 flex-1 sm:max-w-md"
      onSubmit={(e) => {
        e.preventDefault();
        const q = query.trim();
        router.push(q ? `/teams?q=${encodeURIComponent(q)}` : "/teams");
      }}
    >
      <Search
        size={15}
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
      />
      <label htmlFor="shell-search" className="sr-only">
        Search teams
      </label>
      <input
        id="shell-search"
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search teams…"
        className="h-10 w-full rounded-xl border border-border bg-subtle/70 pl-9 pr-3 text-base text-ink placeholder:text-faint focus:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/20 sm:h-9 sm:text-sm"
      />
    </form>
  );
}

function TopBar({ onMenu }: { onMenu: () => void }) {
  const bankroll = useBankroll();
  const today = new Date().toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-canvas/85 px-4 backdrop-blur-md sm:px-6">
      <button
        onClick={onMenu}
        aria-label="Open menu"
        className="-ml-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-hairline hover:text-ink lg:hidden"
      >
        <Menu size={20} />
      </button>
      <TeamSearch />
      <div className="ml-auto flex shrink-0 items-center gap-3">
        <span className="hidden text-sm text-muted md:block">{today}</span>
        {bankroll && bankroll.settledCount > 0 && (
          <span className="flex items-baseline gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-faint">
              P&amp;L
            </span>
            <span className={`text-xs font-semibold tabular-nums ${pnlTone(bankroll.pnl)}`}>
              {formatSignedCurrency(bankroll.pnl, bankroll.currency)}
            </span>
          </span>
        )}
      </div>
    </header>
  );
}

/**
 * Desktop keeps the sidebar fixed; phones get the same list in a drawer opened
 * from the top bar, so every destination is one tap away instead of hiding
 * half of them behind a "More" sheet.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // While the drawer covers the page, the page behind it must not scroll.
  useEffect(() => {
    if (!drawerOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [drawerOpen]);

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-border bg-surface/90 backdrop-blur-xl lg:flex">
        <Link href="/" className="flex h-14 shrink-0 items-center border-b border-border px-5">
          <Wordmark />
        </Link>
        <SidebarBody pathname={pathname} />
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            aria-label="Close menu"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-black/60 backdrop-blur-[2px]"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Menu"
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-border bg-surface shadow-panel"
          >
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
              <Wordmark size="sm" />
              <button
                onClick={() => setDrawerOpen(false)}
                aria-label="Close menu"
                className="-mr-2 flex h-11 w-11 items-center justify-center rounded-lg text-faint transition-colors hover:bg-hairline hover:text-ink"
              >
                <X size={18} />
              </button>
            </div>
            <SidebarBody pathname={pathname} onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </div>
      )}

      <div className="lg:pl-60">
        <TopBar onMenu={() => setDrawerOpen(true)} />
        <main className="page-container pb-12 pt-5 sm:pt-6 lg:pt-8">{children}</main>
      </div>
    </>
  );
}
