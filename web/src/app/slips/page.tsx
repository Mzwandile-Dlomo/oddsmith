import { SavedSlips } from "@/components/slips/SavedSlips";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Slips — Oddsmith" };

export default function SlipsPage() {
  return (
    <>
      <PageHeader
        title="Slips"
        description="Track stakes, settle selections, and measure actual profit and loss."
      />
      <SavedSlips />
    </>
  );
}
