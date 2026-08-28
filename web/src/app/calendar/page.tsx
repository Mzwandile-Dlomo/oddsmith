import { CalendarMonth } from "@/components/calendar/CalendarMonth";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Calendar — Oddsmith" };

export default function CalendarPage() {
  return (
    <>
      <PageHeader
        title="Calendar"
        description="Every match day at a glance — what is on, what the model can build, and what it paid."
      />
      <CalendarMonth />
    </>
  );
}
