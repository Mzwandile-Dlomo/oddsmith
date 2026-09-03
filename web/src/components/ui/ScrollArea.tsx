"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Horizontal scroller for content that has an irreducible minimum width —
 * tables, mostly. It is keyboard focusable (a bare `overflow-x-auto` div is
 * not reachable, so keyboard users cannot pan it) and fades its edges only
 * while there is actually more to see.
 */
export function ScrollArea({
  children,
  label,
  className = "",
}: {
  children: ReactNode;
  /** Names the region for screen readers, e.g. "League validation table". */
  label: string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: false, end: false });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const update = () => {
      const max = el.scrollWidth - el.clientWidth;
      setEdges({ start: el.scrollLeft > 1, end: max > 1 && el.scrollLeft < max - 1 });
    };

    update();
    el.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, []);

  return (
    <div className={`relative ${className}`}>
      <div
        ref={ref}
        tabIndex={0}
        role="region"
        aria-label={label}
        className="scroll-x rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
      >
        {children}
      </div>
      {edges.start && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 left-0 w-6 bg-gradient-to-r from-surface to-transparent"
        />
      )}
      {edges.end && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-surface to-transparent"
        />
      )}
    </div>
  );
}
