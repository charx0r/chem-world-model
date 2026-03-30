import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@/components/ui/table";
import type { MoleculeDetail } from "@/lib/api-types";
import { FormulaDisplay } from "./formula-display";

interface PropertiesTableProps {
  molecule: MoleculeDetail;
}

const PROPERTIES: {
  label: string;
  key: keyof MoleculeDetail;
  format?: (v: unknown) => string;
}[] = [
  { label: "Molecular Formula", key: "mol_formula" },
  {
    label: "Molecular Weight",
    key: "mol_weight",
    format: (v) => `${(v as number).toFixed(2)} g/mol`,
  },
  {
    label: "Exact Mass",
    key: "exact_mass",
    format: (v) => `${(v as number).toFixed(4)} Da`,
  },
  { label: "LogP", key: "logp", format: (v) => (v as number).toFixed(2) },
  {
    label: "TPSA",
    key: "tpsa",
    format: (v) => `${(v as number).toFixed(1)} \u00c5\u00b2`,
  },
  { label: "H-Bond Acceptors", key: "hba" },
  { label: "H-Bond Donors", key: "hbd" },
  { label: "Rotatable Bonds", key: "num_rotatable" },
  { label: "Rings", key: "num_rings" },
  {
    label: "Complexity",
    key: "complexity",
    format: (v) => (v as number).toFixed(1),
  },
  { label: "CAS Number", key: "cas_number" },
];

export function PropertiesTable({ molecule }: PropertiesTableProps) {
  return (
    <Table>
      <TableBody>
        {PROPERTIES.map(({ label, key, format }) => {
          const val = molecule[key];
          if (val == null) return null;
          return (
            <TableRow key={key}>
              <TableCell className="py-1.5 text-muted-foreground">
                {label}
              </TableCell>
              <TableCell className="py-1.5 font-mono text-sm">
                {key === "mol_formula" ? (
                  <FormulaDisplay formula={String(val)} />
                ) : format ? (
                  format(val)
                ) : (
                  String(val)
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
