import { OddsGenerator } from "@/components/generator/OddsGenerator";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Value — Oddsmith" };

export default function GeneratePage() {
  return (
    <>
      <PageHeader
        title="Value Generator"
        description="Find positive-EV selections across the available fixture window."
      />
      <OddsGenerator />
    </>
  );
}
