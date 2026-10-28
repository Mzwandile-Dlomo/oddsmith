import { CalendarMonth } from "@/components/calendar/CalendarMonth";
import { MatchesTabs } from "@/components/matches/MatchesTabs";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Calendar — Oddsmith" };

export default function CalendarPage() {
  return (
    <>
      <PageHeader
        title="Matches"
        description="Every match day at a glance — what is on, what the model can build, and what it paid."
        actions={<MatchesTabs />}
      />
      <CalendarMonth />
    </>
  );
}
