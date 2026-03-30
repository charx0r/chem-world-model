"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ChevronDown, ChevronRight, Database } from "lucide-react";
import Link from "next/link";
import { MoleculeCard } from "@/components/molecule/molecule-card";
import { ExportButton } from "@/components/shared/export-button";
import type { QueryResult } from "@/lib/api-types";

interface QueryResultsProps {
  result: QueryResult;
}

export function QueryResults({ result }: QueryResultsProps) {
  const [showSql, setShowSql] = useState(false);

  const moleculeRows = result.raw_data.filter(
    (row) => row.inchikey && row.canonical_smiles,
  );

  return (
    <div className="space-y-4">
      {/* Answer */}
      <Card>
        <CardContent className="pt-6">
          <p className="whitespace-pre-wrap leading-relaxed">{result.answer}</p>
          {result.citations.length > 0 && (
            <>
              <Separator className="my-3" />
              <div className="flex flex-wrap gap-1">
                {result.citations.map((c, i) => (
                  <Badge key={i} variant="outline" className="text-xs">
                    {c}
                  </Badge>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Stats + Export */}
      {(result.reaction_count > 0 ||
        Object.keys(result.statistics).length > 0 ||
        result.raw_data.length > 0) && (
        <div className="flex flex-wrap items-center gap-2">
          {result.reaction_count > 0 && (
            <Badge variant="secondary">
              {result.reaction_count} reaction
              {result.reaction_count !== 1 ? "s" : ""}
            </Badge>
          )}
          {Object.entries(result.statistics).map(([key, value]) => (
            <Badge key={key} variant="secondary">
              {key}: {String(value)}
            </Badge>
          ))}
          {result.raw_data.length > 0 && (
            <ExportButton data={result.raw_data} filename="query-results" />
          )}
        </div>
      )}

      {/* SQL */}
      <button
        onClick={() => setShowSql(!showSql)}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        {showSql ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        <Database className="h-3.5 w-3.5" />
        Generated SQL
      </button>
      {showSql && (
        <Card>
          <CardContent className="pt-4">
            <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs">
              {result.sql}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Molecule Cards */}
      {moleculeRows.length > 0 && (
        <>
          <Separator />
          <div>
            <h3 className="mb-3 text-sm font-medium text-muted-foreground">
              Molecules ({moleculeRows.length})
            </h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {moleculeRows.map((row) => (
                <MoleculeCard
                  key={row.inchikey as string}
                  inchikey={row.inchikey as string}
                  smiles={row.canonical_smiles as string}
                  name={row.iupac_name as string | null | undefined}
                  formula={row.mol_formula as string | null | undefined}
                  molWeight={row.mol_weight as number | null | undefined}
                />
              ))}
            </div>
          </div>
        </>
      )}

      {/* Raw data table for non-molecule results */}
      {moleculeRows.length === 0 && result.raw_data.length > 0 && (
        <>
          <Separator />
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Results ({result.raw_data.length} rows)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      {Object.keys(result.raw_data[0]).map((key) => (
                        <th
                          key={key}
                          className="px-2 py-1.5 text-left font-medium text-muted-foreground"
                        >
                          {key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.raw_data.slice(0, 50).map((row, i) => (
                      <tr key={i} className="border-b last:border-0">
                        {Object.entries(row).map(([key, val], j) => {
                          const text = val == null ? "\u2014" : String(val);
                          const href =
                            val != null && key === "inchikey"
                              ? `/molecules/${val}`
                              : val != null && key === "reaction_id"
                                ? `/reactions/${val}`
                                : null;
                          return (
                            <td
                              key={j}
                              className="max-w-[200px] truncate px-2 py-1.5 font-mono text-xs"
                            >
                              {href ? (
                                <Link href={href} className="text-primary underline hover:text-primary/80">
                                  {text}
                                </Link>
                              ) : (
                                text
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
