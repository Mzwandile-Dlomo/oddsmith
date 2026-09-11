import { PersonalPool } from "@/components/pool/PersonalPool";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Personal pool — Oddsmith" };

export default function PoolPage() {
  return (
    <>
      <PageHeader
        title="Personal pool"
        description="Your manually favoured straight wins and corner selections, tracked separately from the model."
      />
      <PersonalPool />
    </>
  );
}
