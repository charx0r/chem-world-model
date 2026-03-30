import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, ApiError } from "@/lib/api-client";
import { ReactionScheme } from "@/components/reaction/reaction-scheme";
import { ConditionsTable } from "@/components/reaction/conditions-table";
import { ProvenanceLink } from "@/components/reaction/provenance-link";

export default async function ReactionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let reaction;
  try {
    reaction = await api.getReaction(id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Reaction {reaction.reaction_id}</h1>
        <div className="mt-2 flex flex-wrap gap-2">
          {reaction.reaction_class && (
            <Badge variant="secondary">{reaction.reaction_class}</Badge>
          )}
        </div>
      </div>

      {/* Reaction scheme */}
      {reaction.components.length > 0 && (
        <Card className="mb-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Reaction Scheme</CardTitle>
          </CardHeader>
          <CardContent>
            <ReactionScheme components={reaction.components} />
          </CardContent>
        </Card>
      )}

      {/* Reaction SMILES */}
      {reaction.reaction_smiles && (
        <Card className="mb-6">
          <CardContent className="flex items-center gap-2 py-3">
            <span className="text-sm text-muted-foreground">
              Reaction SMILES:
            </span>
            <code className="flex-1 overflow-x-auto font-mono text-sm">
              {reaction.reaction_smiles}
            </code>
          </CardContent>
        </Card>
      )}

      {/* Conditions */}
      <Card className="mb-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Conditions</CardTitle>
        </CardHeader>
        <CardContent>
          <ConditionsTable reaction={reaction} />

          {/* Additional conditions from the conditions array */}
          {reaction.conditions.length > 0 && (
            <>
              <Separator className="my-3" />
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead className="text-right">Value</TableHead>
                    <TableHead>Unit</TableHead>
                    <TableHead>Phase</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reaction.conditions.map((cond, i) => (
                    <TableRow key={i}>
                      <TableCell>{cond.condition_type}</TableCell>
                      <TableCell className="text-right font-mono">
                        {cond.value?.toFixed(2) ?? "\u2014"}
                      </TableCell>
                      <TableCell>{cond.unit}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {cond.phase ?? "\u2014"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>

      {/* Components table */}
      {reaction.components.length > 0 && (
        <Card className="mb-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Components</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>InChIKey</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead className="text-right">Equivalents</TableHead>
                  <TableHead className="text-right">Mass (g)</TableHead>
                  <TableHead className="text-right">Volume (mL)</TableHead>
                  <TableHead className="text-right">Yield (%)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reaction.components.map((comp) => (
                  <TableRow key={`${comp.inchikey}-${comp.role}`}>
                    <TableCell className="font-mono text-xs">
                      <a
                        href={`/molecules/${comp.inchikey}`}
                        className="text-primary hover:underline"
                      >
                        {comp.inchikey.slice(0, 14)}...
                      </a>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {comp.role}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {comp.equivalents?.toFixed(2) ?? "\u2014"}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {comp.mass_g?.toFixed(3) ?? "\u2014"}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {comp.volume_ml?.toFixed(2) ?? "\u2014"}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {comp.yield_pct?.toFixed(1) ?? "\u2014"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Provenance */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Provenance</CardTitle>
        </CardHeader>
        <CardContent>
          <ProvenanceLink reaction={reaction} />
        </CardContent>
      </Card>
    </div>
  );
}
