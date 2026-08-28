import { ModelLab } from "@/components/model/ModelLab";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata = { title: "Model — Oddsmith" };

export default function ModelPage() {
  return (
    <>
      <PageHeader
        title="Model"
        description="See the evidence, coverage, limitations, and next validation gates."
      />
      <ModelLab />
    </>
  );
}
