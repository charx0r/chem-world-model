"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";
import { exportCSV, exportJSON } from "@/lib/export";

interface ExportButtonProps {
  data: Record<string, unknown>[];
  filename?: string;
}

export function ExportButton({
  data,
  filename = "chemworldmodel-export",
}: ExportButtonProps) {
  const [open, setOpen] = useState(false);

  if (data.length === 0) return null;

  return (
    <div className="relative inline-block">
      <Button
        variant="outline"
        size="sm"
        className="h-7 gap-1 text-xs"
        onClick={() => setOpen(!open)}
      >
        <Download className="h-3.5 w-3.5" />
        Export
      </Button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-50 mt-1 rounded-md border bg-card p-1 shadow-md">
            <button
              className="block w-full rounded px-3 py-1.5 text-left text-sm hover:bg-accent"
              onClick={() => {
                exportCSV(data, `${filename}.csv`);
                setOpen(false);
              }}
            >
              Download CSV
            </button>
            <button
              className="block w-full rounded px-3 py-1.5 text-left text-sm hover:bg-accent"
              onClick={() => {
                exportJSON(data, `${filename}.json`);
                setOpen(false);
              }}
            >
              Download JSON
            </button>
          </div>
        </>
      )}
    </div>
  );
}
