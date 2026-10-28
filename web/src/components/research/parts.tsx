import type { Angle } from "@/lib/types";
import { parseKickoff } from "@/lib/utils";

const STRENGTH_CLASS: Record<Angle["strength"], string> = {
  Strong: "border-success-line bg-success-faint text-success",
  Moderate: "border-warn-line bg-warn-soft/60 text-warn",
  Weak: "border-border bg-hairline text-muted",
};

/** The grade always travels with its count, so 2/3 never reads like 9/10. */
export function StrengthBadge({ angle }: { angle: Angle }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${STRENGTH_CLASS[angle.strength]}`}
    >
      {angle.strength}
      <span className="font-medium tabular-nums opacity-80">
        {angle.hits}/{angle.sample}
      </span>
    </span>
  );
}

const FORM_CLASS: Record<string, string> = {
  W: "bg-success-soft text-success",
  D: "bg-hairline text-muted",
  L: "bg-danger-soft text-danger",
};

/** Results newest first, as small lettered chips (never colour alone). */
export function FormStrip({ form, label }: { form: string[]; label: string }) {
  if (form.length === 0) return <span className="text-xs text-faint">No history</span>;
  return (
    <span className="flex gap-0.5" aria-label={`${label} form, newest first: ${form.join(" ")}`}>
      {form.map((r, i) => (
        <span
          key={i}
          className={`flex h-5 w-5 items-center justify-center rounded text-[10px] font-bold ${FORM_CLASS[r] ?? "bg-hairline text-muted"}`}
        >
          {r}
        </span>
      ))}
    </span>
  );
}

export function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

export function localTime(iso: string): string {
  return parseKickoff(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/**
 * Mirrors research.kickoff_time_known on the API: the schedule feed stores a
 * not-yet-announced kickoff at local midnight (00:00 UTC, or 22:00/23:00 UTC
 * for Ligue 1), hours no top-five league plays at.
 */
export function kickoffTimeKnown(fixture: { provider: string; kickoff_utc: string }): boolean {
  const t = parseKickoff(fixture.kickoff_utc);
  const placeholder = t.getUTCMinutes() === 0 && [22, 23, 0].includes(t.getUTCHours());
  return !(fixture.provider === "fixture_download" && placeholder);
}

/** Short date, with the year whenever it isn't this year (head-to-heads span seasons). */
export function matchDate(iso: string): string {
  const d = parseKickoff(iso);
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }) });
}
