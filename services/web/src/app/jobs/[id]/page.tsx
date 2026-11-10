import { JobView } from "@/components/job-view";

export default async function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-4">
      <h1 className="font-heading text-3xl tracking-tight">Ingestion</h1>
      <JobView id={id} />
    </div>
  );
}
