import { type ButtonHTMLAttributes, type ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}

const variantClasses: Record<string, string> = {
  primary:
    "bg-[#6C47FF] text-white hover:bg-[#5A38E8] active:scale-[0.98] shadow-sm",
  secondary:
    "bg-white text-[#111827] border border-[#E5E7EB] hover:bg-[#F9FAFB] active:scale-[0.98]",
  ghost:
    "bg-transparent text-[#6B7280] hover:bg-[#F3F4F6] hover:text-[#111827] active:scale-[0.98]",
  danger:
    "bg-[#FEE2E2]/60 text-[#DC2626] border border-[#DC2626]/20 hover:bg-[#FEE2E2] active:scale-[0.98]",
};

const sizeClasses: Record<string, string> = {
  sm: "px-3 py-1.5 text-xs rounded-lg",
  md: "px-4 py-2 text-sm rounded-lg",
  lg: "px-5 py-2.5 text-sm rounded-xl",
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
      className={`inline-flex items-center justify-center gap-2 font-medium transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6C47FF]/40 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50 ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
