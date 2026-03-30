import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { GraphPageClient } from "./graph-client";

export default function GraphPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-6">
          <Skeleton className="mb-2 h-8 w-48" />
          <Skeleton className="mb-6 h-4 w-96" />
          <Skeleton className="mb-4 h-10 w-full" />
          <Skeleton className="h-[500px] w-full rounded-lg" />
        </div>
      }
    >
      <GraphPageClient />
    </Suspense>
  );
}
