import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { truncateSmiles } from "@/lib/utils";
import { FormulaDisplay } from "./formula-display";
import { MoleculeStructure } from "./molecule-structure";

interface MoleculeCardProps {
  inchikey: string;
  smiles: string;
  name?: string | null;
  formula?: string | null;
  molWeight?: number | null;
  similarity?: number | null;
}

export function MoleculeCard({
  inchikey,
  smiles,
  name,
  formula,
  molWeight,
  similarity,
}: MoleculeCardProps) {
  return (
    <Link href={`/molecules/${inchikey}`}>
      <Card className="group transition-shadow hover:shadow-md">
        <CardHeader className="p-3 pb-0">
          <div className="flex h-[140px] items-center justify-center rounded border bg-white">
            <MoleculeStructure smiles={smiles} width={200} height={130} />
          </div>
        </CardHeader>
        <CardContent className="p-3 pt-2">
          <CardTitle className="line-clamp-1 text-sm font-medium group-hover:text-primary">
            {name || truncateSmiles(smiles, 30)}
          </CardTitle>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {formula && (
              <FormulaDisplay formula={formula} className="text-xs text-muted-foreground" />
            )}
            {molWeight != null && (
              <Badge variant="secondary" className="text-[10px]">
                {molWeight.toFixed(1)} g/mol
              </Badge>
            )}
            {similarity != null && (
              <Badge variant="outline" className="text-[10px]">
                {(similarity * 100).toFixed(0)}% similar
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
