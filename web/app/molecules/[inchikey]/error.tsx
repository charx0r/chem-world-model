"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function MoleculeError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-16 text-center">
      <h2 className="mb-2 text-xl font-semibold">Could not load molecule</h2>
      <p className="mb-6 text-sm text-muted-foreground">
        {error.message.includes("Database") || error.message.includes("502")
          ? "The molecule was not found or a database error occurred."
          : error.message}
      </p>
      <div className="flex gap-3">
        <Button variant="outline" onClick={reset}>
          Try again
        </Button>
        <Link href="/">
          <Button>Back to search</Button>
        </Link>
      </div>
    </div>
  );
}
