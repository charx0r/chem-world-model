"use client";

import Link from "next/link";
import { MoleculeStructure } from "@/components/molecule/molecule-structure";
import { Badge } from "@/components/ui/badge";
import type { ReactionComponent } from "@/lib/api-types";

interface ReactionSchemeProps {
  components: ReactionComponent[];
}

function groupByRole(components: ReactionComponent[]) {
  const reactants: ReactionComponent[] = [];
  const products: ReactionComponent[] = [];
  const others: ReactionComponent[] = [];

  for (const c of components) {
    const role = c.role.toLowerCase();
    if (role === "reactant" || role === "input") reactants.push(c);
    else if (role === "product" || role === "output") products.push(c);
    else others.push(c);
  }

  return { reactants, products, others };
}

function ComponentCard({ component }: { component: ReactionComponent }) {
  return (
    <Link
      href={`/molecules/${component.inchikey}`}
      className="flex flex-col items-center gap-1"
    >
      <div className="rounded border bg-white p-1">
        {component.canonical_smiles ? (
          <MoleculeStructure
            smiles={component.canonical_smiles}
            width={120}
            height={90}
          />
        ) : (
          <div className="flex h-[90px] w-[120px] items-center justify-center text-xs text-muted-foreground">
            No structure
          </div>
        )}
      </div>
      <span className="max-w-[120px] truncate text-center text-[10px] text-muted-foreground">
        {component.inchikey.slice(0, 14)}
      </span>
    </Link>
  );
}

export function ReactionScheme({ components }: ReactionSchemeProps) {
  const { reactants, products, others } = groupByRole(components);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-center gap-2">
        {/* Reactants */}
        {reactants.map((c, i) => (
          <div key={c.inchikey} className="flex items-center gap-2">
            {i > 0 && (
              <span className="text-lg font-light text-muted-foreground">
                +
              </span>
            )}
            <ComponentCard component={c} />
          </div>
        ))}

        {/* Arrow */}
        <div className="flex flex-col items-center px-4">
          <span className="text-2xl text-muted-foreground">⟶</span>
          {others.length > 0 && (
            <div className="flex flex-wrap justify-center gap-1">
              {others.map((c) => (
                <Badge
                  key={c.inchikey}
                  variant="outline"
                  className="text-[10px]"
                >
                  {c.role}
                </Badge>
              ))}
            </div>
          )}
        </div>

        {/* Products */}
        {products.map((c, i) => (
          <div key={c.inchikey} className="flex items-center gap-2">
            {i > 0 && (
              <span className="text-lg font-light text-muted-foreground">
                +
              </span>
            )}
            <ComponentCard component={c} />
          </div>
        ))}
      </div>
    </div>
  );
}
