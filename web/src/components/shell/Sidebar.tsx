"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  FlaskConical,
  LayoutGrid,
  ListChecks,
  Pin,
  MoreHorizontal,
  Sparkles,
  Sun,
  Trophy,
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

/** Ordered by the daily routine: check today, plan ahead, then review. */
const PRIMARY: NavItem[] = [
  { href: "/today", label: "Today", icon: Sun, hint: "Today's slip and card" },
  { href: "/calendar", label: "Calendar", icon: CalendarDays, hint: "Plan and review by day" },
  { href: "/slips", label: "Slips", icon: ListChecks, hint: "Open bets and settling" },
  { href: "/results", label: "Results", icon: Trophy, hint: "Settled outcomes and history" },
];

const SECONDARY: NavItem[] = [
  { href: "/build", label: "Build", icon: LayoutGrid, hint: "Manual bet builder" },
  { href: "/pool", label: "Pool", icon: Pin, hint: "Personal favourable selections" },
  { href: "/generate", label: "Value", icon: Sparkles, hint: "Positive-EV selections" },
  { href: "/model", label: "Model", icon: FlaskConical, hint: "Evidence and validation" },
];

function isActive(pathname: string, href: string): boolean {
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
function useBankroll() {
  const { data: slips } = useQuery({ queryKey: ["slips"], queryFn: fetchSlips });
  if (!slips) return null;

  const settled = slips.filter((s) => s.result !== "pending");
  const pending = slips.filter((s) => s.result === "pending");
  return {
    pnl: settled.reduce((acc, s) => acc + s.profit_loss, 0),
    atRisk: pending.reduce((acc, s) => acc + s.stake, 0),
    settledCount: settled.length,
    pendingCount: pending.length,
    currency: slips[0]?.currency ?? "USD",
  };
}

function pnlTone(pnl: number): string {
  return pnl > 0 ? "text-success" : pnl < 0 ? "text-danger" : "text-ink";
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      title={item.hint}
      aria-current={active ? "page" : undefined}
      className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
        active
          ? "bg-accent-light text-accent shadow-[inset_3px_0_0_#d8ff45]"
          : "text-muted hover:bg-hairline hover:text-ink"
      }`}
    >
      <Icon
        size={16}
        className={`shrink-0 ${active ? "text-accent" : "text-faint group-hover:text-muted"}`}
      />
      {item.label}
    </Link>
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

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-border bg-surface/90 backdrop-blur-xl lg:flex">
      <div className="flex h-20 shrink-0 items-center border-b border-border px-5">
        <Wordmark />
      </div>

      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
        {PRIMARY.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(pathname, item.href)} />
        ))}

        <p className="mt-7 mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-faint">
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

/**
 * Mobile chrome is split in two: a slim bar that only carries identity and the
 * bankroll figure, and a thumb-reachable tab bar pinned to the bottom. The old
 * scrolling pill row cost ~90px of vertical space and hid half the destinations
 * off the right edge.
 */
export function MobileTopBar() {
  const bankroll = useBankroll();

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-border bg-canvas/85 px-4 backdrop-blur-md lg:hidden">
      <Wordmark size="sm" />
      {bankroll && bankroll.settledCount > 0 && (
        <span className="flex items-baseline gap-1.5 rounded-full border border-border bg-canvas px-2.5 py-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-faint">
            P&amp;L
          </span>
          <span className={`text-xs font-semibold tabular-nums ${pnlTone(bankroll.pnl)}`}>
            {formatSignedCurrency(bankroll.pnl, bankroll.currency)}
          </span>
        </span>
      )}
    </header>
  );
}

function TabButton({
  active,
  label,
  icon: Icon,
  ...rest
}: {
  active: boolean;
  label: string;
  icon: React.ElementType;
} & React.ComponentProps<"button">) {
  return (
    <button
      {...rest}
      className={`flex min-h-[56px] flex-col items-center justify-center gap-1 px-1 transition-colors duration-150 focus:outline-none focus-visible:bg-hairline ${
        active ? "text-accent" : "text-faint"
      }`}
    >
      <Icon size={20} className="shrink-0" />
      <span className="text-[10px] font-medium leading-none">{label}</span>
    </button>
  );
}

export function MobileTabBar() {
  const pathname = usePathname();
  const [sheetOpen, setSheetOpen] = useState(false);
  const bankroll = useBankroll();

  // While the sheet covers the page, the page behind it must not scroll.
  useEffect(() => {
    if (!sheetOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSheetOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [sheetOpen]);

  const toolsActive = SECONDARY.some((item) => isActive(pathname, item.href));

  return (
    <>
      {sheetOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            aria-label="Close menu"
            onClick={() => setSheetOpen(false)}
            className="absolute inset-0 bg-ink/30 backdrop-blur-[2px]"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="More"
            className="absolute inset-x-0 bottom-0 rounded-t-2xl border-t border-border bg-surface pb-safe shadow-sheet"
          >
            <div className="flex items-center justify-between px-5 pt-4 pb-2">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-faint">
                Tools
              </p>
              <button
                onClick={() => setSheetOpen(false)}
                aria-label="Close menu"
                className="-mr-2 flex h-11 w-11 items-center justify-center rounded-lg text-faint transition-colors hover:bg-hairline hover:text-ink"
              >
                <X size={18} />
              </button>
            </div>

            <nav className="flex flex-col px-3 pb-2">
              {SECONDARY.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setSheetOpen(false)}
                    aria-current={active ? "page" : undefined}
                    className={`flex min-h-[52px] items-center gap-3 rounded-xl px-3 ${
                      active ? "bg-accent-light text-accent" : "text-ink"
                    }`}
                  >
                    <Icon size={18} className={active ? "text-accent" : "text-faint"} />
                    <span className="flex flex-col">
                      <span className="text-sm font-medium leading-tight">{item.label}</span>
                      <span className="text-[11px] leading-tight text-faint">{item.hint}</span>
                    </span>
                  </Link>
                );
              })}
            </nav>

            {bankroll && (
              <div className="mx-3 mb-4 flex items-center justify-between rounded-xl border border-border bg-canvas px-4 py-3">
                <span className="flex flex-col">
                  <span className="text-[10px] font-semibold uppercase tracking-widest text-faint">
                    Net profit / loss
                  </span>
                  <span className="text-[11px] text-muted">
                    {bankroll.settledCount} settled
                    {bankroll.pendingCount > 0 &&
                      ` · ${bankroll.currency} ${bankroll.atRisk.toFixed(2)} at risk`}
                  </span>
                </span>
                <span
                  className={`text-lg font-semibold tabular-nums ${pnlTone(bankroll.pnl)}`}
                >
                  {bankroll.settledCount === 0
                    ? "—"
                    : formatSignedCurrency(bankroll.pnl, bankroll.currency)}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-border bg-surface/95 pb-safe backdrop-blur-md lg:hidden">
        {PRIMARY.map((item) => {
          const active = isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-[56px] flex-col items-center justify-center gap-1 px-1 transition-colors duration-150 ${
                active ? "text-accent" : "text-faint"
              }`}
            >
              <Icon size={20} className="shrink-0" />
              <span className="text-[10px] font-medium leading-none">{item.label}</span>
            </Link>
          );
        })}
        <TabButton
          active={toolsActive || sheetOpen}
          label="More"
          icon={MoreHorizontal}
          onClick={() => setSheetOpen((v) => !v)}
          aria-haspopup="dialog"
          aria-expanded={sheetOpen}
        />
      </nav>
    </>
  );
}
