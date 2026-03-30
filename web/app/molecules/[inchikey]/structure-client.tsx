"use client";

import { MoleculeStructure } from "@/components/molecule/molecule-structure";

export function MoleculeStructureClient(props: {
  smiles: string;
  width?: number;
  height?: number;
}) {
  return <MoleculeStructure {...props} />;
}
