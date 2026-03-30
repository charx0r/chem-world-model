"use client";

import { useEffect, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useRDKit } from "@/hooks/use-rdkit";

interface MoleculeStructureProps {
  smiles: string;
  width?: number;
  height?: number;
}

export function MoleculeStructure({
  smiles,
  width = 250,
  height = 200,
}: MoleculeStructureProps) {
  const { rdkit, loading } = useRDKit();
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!rdkit || !smiles) return;

    try {
      const mol = rdkit.get_mol(smiles);
      if (!mol) {
        setError(true);
        return;
      }
      const svgText = mol.get_svg(width, height);
      mol.delete();
      setSvg(svgText);
      setError(false);
    } catch {
      setError(true);
    }
  }, [rdkit, smiles, width, height]);

  if (loading) {
    return <Skeleton className="rounded" style={{ width, height }} />;
  }

  if (error || !svg) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-2 rounded border border-dashed border-border bg-muted/30 text-muted-foreground"
        style={{ width, height }}
      >
        <span className="text-xs">Structure unavailable</span>
        <span className="max-w-full truncate px-2 font-mono text-[10px]">
          {smiles}
        </span>
      </div>
    );
  }

  return (
    <div
      className="molecule-svg rounded bg-white"
      style={{ width, height }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
