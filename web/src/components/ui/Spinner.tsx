export function Spinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const s =
    size === "sm" ? "h-4 w-4" : size === "lg" ? "h-8 w-8" : "h-6 w-6";
  return (
    <svg
      className={`${s} animate-spin text-[#6C47FF]`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

export function SpinnerOverlay({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-[#9CA3AF]">
      <Spinner size="lg" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06)] animate-pulse">
      <div className="mb-3 h-4 w-3/5 rounded-lg bg-[#F3F4F6]" />
      <div className="mb-2 h-3 w-2/5 rounded-lg bg-[#F3F4F6]" />
      <div className="flex gap-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-10 w-20 rounded-xl bg-[#F3F4F6]" />
        ))}
      </div>
    </div>
  );
}
