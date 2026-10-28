import { AnalyticsView } from "@/components/analytics/AnalyticsView";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Analytics — Oddsmith" };

export default function AnalyticsPage() {
  return (
    <>
      <PageHeader
        title="Analytics"
        description="How your settled slips have actually done, and how far the model's paper track has come."
      />
      <AnalyticsView />
    </>
  );
}
