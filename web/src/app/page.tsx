import { MatchesTabs } from "@/components/matches/MatchesTabs";
import { ResearchFeed } from "@/components/research/ResearchFeed";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Matches — Oddsmith" };

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export default async function MatchesHome({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  return (
    <>
      <PageHeader
        title="Matches"
        description="Each match's recent form, previous games and over/under trends, with a written read. Place any bet on your bookmaker's own site."
        actions={<MatchesTabs />}
      />
      {/* Keyed by day so filters reset when you move to another date. */}
      <ResearchFeed key={date ?? "today"} initialDay={date && ISO_DATE.test(date) ? date : null} />
    </>
  );
}
