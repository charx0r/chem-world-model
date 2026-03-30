"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import { MoleculeCard } from "@/components/molecule/molecule-card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { cn, formatNumber, truncateSmiles, yieldColor } from "@/lib/utils";
import type {
  MoleculeDetail,
  MoleculeSearchResult,
  ReactionDetail,
  ReactionSearchResult,
} from "@/lib/api-types";

type Tab = "molecules" | "reactions";

const PAGE_SIZE = 24;
const REACTION_PAGE_SIZE = 20;

export default function BrowsePage() {
  const [tab, setTab] = useState<Tab>("molecules");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Molecule state
  const [molecules, setMolecules] = useState<MoleculeDetail[]>([]);
  const [molTotal, setMolTotal] = useState(0);
  const [molOffset, setMolOffset] = useState(0);
  const [molLoading, setMolLoading] = useState(false);

  // Reaction state
  const [reactions, setReactions] = useState<ReactionDetail[]>([]);
  const [rxnTotal, setRxnTotal] = useState(0);
  const [rxnOffset, setRxnOffset] = useState(0);
  const [rxnLoading, setRxnLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  // Debounce search input
  const handleQueryChange = useCallback((value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(value);
      setMolOffset(0);
      setRxnOffset(0);
    }, 300);
  }, []);

  // Fetch molecules
  const fetchMolecules = useCallback(async (q: string, offset: number) => {
    setMolLoading(true);
    setError(null);
    try {
      const res = await api.browseMolecules({
        q: q || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setMolecules(res.molecules);
      setMolTotal(res.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load molecules");
    } finally {
      setMolLoading(false);
    }
  }, []);

  // Fetch reactions
  const fetchReactions = useCallback(async (q: string, offset: number) => {
    setRxnLoading(true);
    setError(null);
    try {
      const res = await api.browseReactions({
        q: q || undefined,
        limit: REACTION_PAGE_SIZE,
        offset,
      });
      setReactions(res.reactions);
      setRxnTotal(res.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load reactions");
    } finally {
      setRxnLoading(false);
    }
  }, []);

  // Load data when tab, query, or offset changes
  useEffect(() => {
    if (tab === "molecules") fetchMolecules(debouncedQuery, molOffset);
  }, [tab, debouncedQuery, molOffset, fetchMolecules]);

  useEffect(() => {
    if (tab === "reactions") fetchReactions(debouncedQuery, rxnOffset);
  }, [tab, debouncedQuery, rxnOffset, fetchReactions]);

  const isLoading = tab === "molecules" ? molLoading : rxnLoading;
  const total = tab === "molecules" ? molTotal : rxnTotal;
  const offset = tab === "molecules" ? molOffset : rxnOffset;
  const pageSize = tab === "molecules" ? PAGE_SIZE : REACTION_PAGE_SIZE;
  const setOffset = tab === "molecules" ? setMolOffset : setRxnOffset;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="mb-2 font-serif text-3xl font-semibold tracking-tight">
          Browse
        </h1>
        <p className="text-sm text-muted-foreground">
          Explore {formatNumber(507546)} molecules and{" "}
          {formatNumber(419000)} reactions in the knowledge graph.
        </p>
      </div>

      {/* Tabs + Search */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-1">
          <button
            onClick={() => setTab("molecules")}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              tab === "molecules"
                ? "bg-accent font-medium text-accent-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            Molecules
          </button>
          <button
            onClick={() => setTab("reactions")}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              tab === "reactions"
                ? "bg-accent font-medium text-accent-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            Reactions
          </button>
        </div>

        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder={
              tab === "molecules"
                ? "Search by name..."
                : "Search in reaction SMILES..."
            }
            className="h-9 w-full rounded-md border bg-background px-3 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/50 sm:w-72"
          />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Results count + pagination */}
      <div className="mb-4 flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {isLoading
            ? "Loading..."
            : `${formatNumber(total)} result${total === 1 ? "" : "s"}`}
          {debouncedQuery && ` for "${debouncedQuery}"`}
        </span>
        {total > pageSize && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setOffset(Math.max(0, offset - pageSize))}
              disabled={offset === 0}
              className="rounded border px-2 py-1 transition-colors hover:bg-accent disabled:opacity-40"
            >
              Prev
            </button>
            <span>
              {Math.floor(offset / pageSize) + 1} /{" "}
              {Math.ceil(total / pageSize)}
            </span>
            <button
              onClick={() => setOffset(offset + pageSize)}
              disabled={offset + pageSize >= total}
              className="rounded border px-2 py-1 transition-colors hover:bg-accent disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </div>

      <Separator className="mb-6" />

      {/* Molecule grid */}
      {tab === "molecules" && (
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {molecules.map((mol) => (
            <MoleculeCard
              key={mol.inchikey}
              inchikey={mol.inchikey}
              smiles={mol.canonical_smiles}
              name={mol.iupac_name}
              formula={mol.mol_formula}
              molWeight={mol.mol_weight}
            />
          ))}
          {!isLoading && molecules.length === 0 && (
            <p className="col-span-full py-12 text-center text-sm text-muted-foreground">
              No molecules found.
            </p>
          )}
        </div>
      )}

      {/* Reaction list */}
      {tab === "reactions" && (
        <div className="grid gap-3">
          {reactions.map((rxn) => (
            <Link key={rxn.reaction_id} href={`/reactions/${rxn.reaction_id}`}>
              <Card className="group transition-shadow hover:shadow-md">
                <CardContent className="flex items-center gap-4 p-4">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-foreground">
                      {rxn.reaction_smiles
                        ? truncateSmiles(rxn.reaction_smiles, 80)
                        : rxn.reaction_id}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      {rxn.reaction_class && (
                        <Badge variant="secondary" className="text-[10px]">
                          {rxn.reaction_class}
                        </Badge>
                      )}
                      {rxn.atmosphere && (
                        <Badge variant="outline" className="text-[10px]">
                          {rxn.atmosphere}
                        </Badge>
                      )}
                      {rxn.temperature_c != null && (
                        <span className="text-[10px] text-muted-foreground">
                          {rxn.temperature_c}&deg;C
                        </span>
                      )}
                      {rxn.doi && (
                        <span className="text-[10px] text-muted-foreground">
                          DOI
                        </span>
                      )}
                    </div>
                  </div>
                  {rxn.yield_pct != null && (
                    <span
                      className={cn(
                        "shrink-0 font-mono text-sm font-medium",
                        yieldColor(rxn.yield_pct),
                      )}
                    >
                      {rxn.yield_pct.toFixed(0)}%
                    </span>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
          {!isLoading && reactions.length === 0 && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No reactions found.
            </p>
          )}
        </div>
      )}

      {/* Bottom pagination */}
      {total > pageSize && (
        <>
          <Separator className="my-6" />
          <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
            <button
              onClick={() => setOffset(Math.max(0, offset - pageSize))}
              disabled={offset === 0}
              className="rounded border px-2 py-1 transition-colors hover:bg-accent disabled:opacity-40"
            >
              Prev
            </button>
            <span>
              Page {Math.floor(offset / pageSize) + 1} of{" "}
              {Math.ceil(total / pageSize)}
            </span>
            <button
              onClick={() => setOffset(offset + pageSize)}
              disabled={offset + pageSize >= total}
              className="rounded border px-2 py-1 transition-colors hover:bg-accent disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
