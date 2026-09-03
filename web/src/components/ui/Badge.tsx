import { type ReactNode } from "react";

interface BadgeProps {
  children: ReactNode;
  className?: string;
  /** Hover text — used to explain a state the label alone can't carry. */
  title?: string;
}

export function Badge({ children, className = "", title }: BadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize ${className}`}
    >
      {children}
    </span>
  );
}
