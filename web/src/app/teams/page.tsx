import { PageHeader } from "@/components/shell/PageHeader";
import { TeamsView } from "@/components/teams/TeamsView";

export const metadata = { title: "Teams — Oddsmith" };

export default async function TeamsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  return (
    <>
      <PageHeader title="Teams" description="Every club in the five leagues, ranked by this season's table." />
      {/* Keyed by the query so a new top-bar search resets the filter box. */}
      <TeamsView key={q ?? ""} initialQuery={q ?? ""} />
    </>
  );
}
