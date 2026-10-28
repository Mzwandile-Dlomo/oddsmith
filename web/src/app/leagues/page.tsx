import { LeaguesView } from "@/components/leagues/LeaguesView";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Leagues — Oddsmith" };

export default async function LeaguesPage({
  searchParams,
}: {
  searchParams: Promise<{ league?: string }>;
}) {
  const { league } = await searchParams;
  return (
    <>
      <PageHeader
        title="Leagues"
        description="Standings built from stored results, and the latest scores."
      />
      <LeaguesView initialLeague={league || "EPL"} />
    </>
  );
}
