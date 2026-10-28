import { MatchView } from "@/components/matches/MatchView";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export const metadata = { title: "Match — Oddsmith" };

export default async function MatchPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ date?: string }>;
}) {
  const { id } = await params;
  const { date } = await searchParams;
  return (
    <MatchView
      id={decodeURIComponent(id)}
      date={date && ISO_DATE.test(date) ? date : null}
    />
  );
}
