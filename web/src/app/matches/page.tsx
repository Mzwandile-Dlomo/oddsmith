import { MatchesTabs } from "@/components/matches/MatchesTabs";
import { MatchesView } from "@/components/matches/MatchesView";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Matches — Oddsmith" };

export default function MatchesPage() {
  return (
    <>
      <PageHeader
        title="Matches"
        description="Upcoming fixtures with bookmaker and model prices. Open a match for its full page."
        actions={<MatchesTabs />}
      />
      <MatchesView />
    </>
  );
}
