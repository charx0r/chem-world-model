import { MoleculeCard } from "./molecule-card";
import type { SimilarMoleculeHit } from "@/lib/api-types";

interface SimilarMoleculesProps {
  molecules: SimilarMoleculeHit[];
}

export function SimilarMolecules({ molecules }: SimilarMoleculesProps) {
  if (molecules.length === 0) {
    return (
      <p className="py-4 text-sm text-muted-foreground">
        No similar molecules found.
      </p>
    );
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {molecules.map((m) => (
        <div key={m.inchikey} className="w-[180px] shrink-0">
          <MoleculeCard
            inchikey={m.inchikey}
            smiles={m.canonical_smiles}
            similarity={m.tanimoto}
          />
        </div>
      ))}
    </div>
  );
}
