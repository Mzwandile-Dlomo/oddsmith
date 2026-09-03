import { type ButtonHTMLAttributes, type ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}

const variantClasses: Record<string, string> = {
  primary:
    "bg-accent text-white hover:bg-accent-hover active:scale-[0.98] shadow-sm",
  secondary:
    "bg-surface text-ink border border-border hover:bg-subtle active:scale-[0.98]",
  ghost:
    "bg-transparent text-muted hover:bg-hairline hover:text-ink active:scale-[0.98]",
  danger:
    "bg-danger-soft/60 text-danger border border-danger/20 hover:bg-danger-soft active:scale-[0.98]",
};

/**
 * Touch targets clear 44px on phones and tighten up from `sm` where a pointer
 * is doing the aiming. `min-h` rather than `py` so the height is guaranteed
 * regardless of what the label wraps to.
 */
const sizeClasses: Record<string, string> = {
  sm: "min-h-[44px] px-3 text-xs rounded-lg sm:min-h-[32px]",
  md: "min-h-[44px] px-4 text-sm rounded-lg sm:min-h-[38px]",
  lg: "min-h-[48px] px-5 text-sm rounded-xl sm:min-h-[44px]",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled}
      className={`inline-flex shrink-0 items-center justify-center gap-2 font-medium transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50 ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
