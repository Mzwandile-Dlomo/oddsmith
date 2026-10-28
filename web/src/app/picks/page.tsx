import { PicksView } from "@/components/picks/PicksView";
import { PICK_TABS, type PickTab } from "@/components/picks/tabs";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Picks — Oddsmith" };

export default async function PicksPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;
  const active: PickTab = PICK_TABS.find((t) => t === tab) ?? "daily";
  return (
    <>
      <PageHeader
        title="Picks"
        description="Model-built slips and your own favourites. Probability first, price second."
      />
      <PicksView tab={active} />
    </>
  );
}
