import { Skeleton } from "@/components/ui/skeleton";

export default function ReactionLoading() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <Skeleton className="mb-2 h-8 w-64" />
      <Skeleton className="mb-6 h-6 w-32" />
      <Skeleton className="mb-6 h-[200px] rounded-lg" />
      <Skeleton className="mb-6 h-[100px] rounded-lg" />
      <Skeleton className="h-[200px] rounded-lg" />
    </div>
  );
}
