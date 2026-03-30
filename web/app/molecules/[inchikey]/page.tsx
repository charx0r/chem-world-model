import { notFound } from "next/navigation";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api-client";
import { FormulaDisplay } from "@/components/molecule/formula-display";
import { PropertiesTable } from "@/components/molecule/properties-table";
import { HazardBadges } from "@/components/molecule/hazard-badges";
import { SimilarMolecules } from "@/components/molecule/similar-molecules";
import { MoleculeStructureClient } from "./structure-client";
import { ExternalLinks } from "./external-links";

export default async function MoleculeDetailPage({
  params,
}: {
  params: Promise<{ inchikey: string }>;
}) {
  const { inchikey } = await params;

  let molecule;
  try {
    molecule = await api.getMolecule(inchikey);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">
            {molecule.iupac_name || molecule.inchikey}
          </h1>
          {molecule.iupac_name && (
            <p className="mt-1 font-mono text-sm text-muted-foreground">
              {molecule.inchikey}
            </p>
          )}
          {molecule.mol_formula && (
            <FormulaDisplay
              formula={molecule.mol_formula}
              className="mt-2 block text-lg tracking-wide"
            />
          )}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {molecule.commercially_available && (
              <Badge className="bg-green-100 text-green-800">
                Commercially Available
              </Badge>
            )}
            {molecule.sources.map((s) => (
              <Badge key={s} variant="secondary">
                {s}
              </Badge>
            ))}
          </div>
        </div>
        <Link href={`/graph?target=${molecule.inchikey}`}>
          <Button variant="outline" size="sm">
            View in Graph
          </Button>
        </Link>
      </div>

      {/* Main content: structure + properties */}
      <div className="mb-6 grid gap-6 lg:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Structure</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-center">
            <MoleculeStructureClient
              smiles={molecule.canonical_smiles}
              width={380}
              height={280}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Properties</CardTitle>
          </CardHeader>
          <CardContent>
            <PropertiesTable molecule={molecule} />
            <ExternalLinks molecule={molecule} />
          </CardContent>
        </Card>
      </div>

      {/* SMILES */}
      <Card className="mb-6">
        <CardContent className="flex items-center gap-2 py-3">
          <span className="text-sm text-muted-foreground">SMILES:</span>
          <code className="flex-1 overflow-x-auto font-mono text-sm">
            {molecule.canonical_smiles}
          </code>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="reactions">
        <TabsList>
          <TabsTrigger value="reactions">
            Reactions ({molecule.reactions.length})
          </TabsTrigger>
          <TabsTrigger value="bioactivities">
            Bioactivities ({molecule.bioactivities.length})
          </TabsTrigger>
          <TabsTrigger value="hazards">
            Hazards ({molecule.hazards.length})
          </TabsTrigger>
          <TabsTrigger value="similar">
            Similar ({molecule.similar.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="reactions" className="mt-4">
          {molecule.reactions.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">
              No reactions found.
            </p>
          ) : (
            <div className="space-y-2">
              {molecule.reactions.map((rxn) => (
                <Link
                  key={rxn.reaction_id}
                  href={`/reactions/${rxn.reaction_id}`}
                  className="block"
                >
                  <Card className="transition-shadow hover:shadow-sm">
                    <CardContent className="flex items-center justify-between py-3">
                      <div>
                        <span className="font-mono text-sm">
                          {rxn.reaction_id}
                        </span>
                        {rxn.reaction_class && (
                          <Badge variant="secondary" className="ml-2 text-xs">
                            {rxn.reaction_class}
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge variant="outline" className="text-xs">
                          {rxn.role}
                        </Badge>
                        {rxn.yield_pct != null && (
                          <span className="font-mono text-sm">
                            {rxn.yield_pct.toFixed(1)}%
                          </span>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="bioactivities" className="mt-4">
          {molecule.bioactivities.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">
              No bioactivity data available.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">
                      Target
                    </th>
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">
                      Organism
                    </th>
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">
                      Type
                    </th>
                    <th className="px-2 py-1.5 text-right font-medium text-muted-foreground">
                      Value
                    </th>
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">
                      Unit
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {molecule.bioactivities.map((bio, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="px-2 py-1.5">
                        {bio.target_name ?? "\u2014"}
                      </td>
                      <td className="px-2 py-1.5 text-muted-foreground">
                        {bio.target_organism ?? "\u2014"}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {bio.activity_type}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono">
                        {bio.value?.toFixed(2) ?? "\u2014"}
                      </td>
                      <td className="px-2 py-1.5 text-muted-foreground">
                        {bio.unit ?? "\u2014"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="hazards" className="mt-4">
          <HazardBadges hazards={molecule.hazards} />
          {molecule.hazards.length === 0 && (
            <p className="py-4 text-sm text-muted-foreground">
              No hazard data available.
            </p>
          )}
        </TabsContent>

        <TabsContent value="similar" className="mt-4">
          <SimilarMolecules molecules={molecule.similar} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
