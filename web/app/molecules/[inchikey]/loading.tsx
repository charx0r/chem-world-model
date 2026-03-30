import { Skeleton } from "@/components/ui/skeleton";

export default function MoleculeLoading() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <Skeleton className="mb-2 h-8 w-64" />
      <Skeleton className="mb-6 h-4 w-96" />
      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-[340px] rounded-lg" />
        <Skeleton className="h-[340px] rounded-lg" />
      </div>
      <Skeleton className="mb-6 h-12 rounded-lg" />
      <Skeleton className="h-[200px] rounded-lg" />
    </div>
  );
}
