import { type ReactNode } from "react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-[#E5E7EB] bg-white px-6 py-14 text-center">
      {icon && (
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#F3F4F6] text-[#9CA3AF]">
          {icon}
        </div>
      )}
      <p className="text-sm font-semibold text-[#111827]">{title}</p>
      {description && (
        <p className="max-w-xs text-sm text-[#9CA3AF]">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
