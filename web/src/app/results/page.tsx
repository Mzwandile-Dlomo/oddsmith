import { ResultsView } from "@/components/history/ResultsView";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Results — Oddsmith" };

export default function ResultsPage() {
  return (
    <>
      <PageHeader
        title="Results"
        description="Inspect historical matches, team form, and the model's source data."
      />
      <ResultsView />
    </>
  );
}
