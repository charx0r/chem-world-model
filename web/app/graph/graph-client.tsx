"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Search, Loader2 } from "lucide-react";
import { GraphControls } from "@/components/graph/graph-controls";
import { GraphLegend } from "@/components/graph/graph-legend";
import { api, ApiError } from "@/lib/api-client";
import type { RouteSearchResult } from "@/lib/api-types";
import type { Core } from "cytoscape";

const GraphExplorer = dynamic(
  () =>
    import("@/components/graph/graph-explorer").then(
      (mod) => mod.GraphExplorer,
    ),
  {
    ssr: false,
    loading: () => <Skeleton className="h-[500px] w-full rounded-lg" />,
  },
);

function friendlyError(message: string): string {
  if (message.includes("sqlalchemy") || message.includes("SQL:")) {
    return "Failed to query the graph database. The molecule may not exist in the graph, or there may be a database configuration issue.";
  }
  if (message.includes("404") || message.includes("not found")) {
    return "Molecule not found in the graph. Check the InChIKey and try again.";
  }
  return message;
}

export function GraphPageClient() {
  const searchParams = useSearchParams();
  const initialTarget = searchParams.get("target") ?? "";

  const [target, setTarget] = useState(initialTarget);
  const [maxDepth, setMaxDepth] = useState(8);
  const [maxRoutes, setMaxRoutes] = useState(10);
  const [data, setData] = useState<RouteSearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cyRef = useRef<Core | null>(null);

  // B4 fix: accept depth/routes as params to avoid stale closure
  const fetchRoutes = useCallback(
    async (inchikey: string, depth?: number, routes?: number) => {
      if (!inchikey.trim()) return;
      setLoading(true);
      setError(null);
      try {
        const result = await api.getRoutes(
          inchikey.trim(),
          depth ?? maxDepth,
          routes ?? maxRoutes,
        );
        setData(result);
      } catch (e) {
        if (e instanceof ApiError) {
          setError(friendlyError(e.message));
        } else {
          setError("Failed to fetch routes. Is the API running?");
        }
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [maxDepth, maxRoutes],
  );

  useEffect(() => {
    if (initialTarget) {
      fetchRoutes(initialTarget);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchRoutes(target);
  };

  const handleNodeSelect = useCallback(
    (inchikey: string) => {
      setTarget(inchikey);
      fetchRoutes(inchikey);
    },
    [fetchRoutes],
  );

  // B5 fix: wire up Fit View
  const handleFitView = useCallback(() => {
    cyRef.current?.fit(undefined, 30);
  }, []);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6">
        <h1 className="mb-2 text-2xl font-semibold">Graph Explorer</h1>
        <p className="text-sm text-muted-foreground">
          Explore retrosynthetic routes by entering a molecule InChIKey. Click
          molecule nodes to navigate the synthesis graph.
        </p>
      </div>

      {/* Search */}
      <form onSubmit={handleSubmit} className="mb-4 flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Enter InChIKey (e.g., BSYNRYMUTXBXSQ-UHFFFAOYSA-N)"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button type="submit" disabled={loading || !target.trim()}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Explore"}
        </Button>
      </form>

      {/* Controls */}
      <div className="mb-4">
        <GraphControls
          maxDepth={maxDepth}
          onMaxDepthChange={(d) => {
            setMaxDepth(d);
            // B4 fix: pass new depth directly
            if (target.trim()) fetchRoutes(target, d, maxRoutes);
          }}
          maxRoutes={maxRoutes}
          onMaxRoutesChange={setMaxRoutes}
          onFitView={handleFitView}
          routeCount={data?.route_count ?? 0}
        />
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 flex items-start justify-between rounded-lg border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="ml-2 shrink-0 text-destructive/70 hover:text-destructive"
          >
            &times;
          </button>
        </div>
      )}

      {/* Graph */}
      <Card className="mb-4">
        <CardContent className="p-0">
          {loading ? (
            <div className="flex h-[500px] items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : data ? (
            <GraphExplorer
              data={data}
              onNodeSelect={handleNodeSelect}
              onCyInit={(cy) => { cyRef.current = cy; }}
            />
          ) : !error ? (
            /* B6 fix: only show empty state when no error */
            <div className="flex h-[500px] items-center justify-center text-sm text-muted-foreground">
              Enter a molecule InChIKey above to explore its synthesis routes.
            </div>
          ) : (
            <div className="h-[500px]" />
          )}
        </CardContent>
      </Card>

      {/* Legend */}
      <GraphLegend />

      {/* Route details */}
      {data && data.routes.length > 0 && (
        <>
          <Separator className="my-6" />
          <h2 className="mb-4 text-lg font-semibold">
            Routes ({data.route_count})
          </h2>
          <div className="space-y-3">
            {data.routes.map((route, i) => (
              <Card key={i}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">
                    Route {i + 1} &mdash; {route.step_count} step
                    {route.step_count !== 1 ? "s" : ""}
                    {route.cumulative_yield != null && (
                      <span className="ml-2 font-mono text-xs text-muted-foreground">
                        ({route.cumulative_yield.toFixed(1)}% cumulative yield)
                      </span>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    {route.starting_materials.map((sm) => (
                      <a
                        key={sm.inchikey}
                        href={`/molecules/${sm.inchikey}`}
                        className="rounded border px-2 py-1 font-mono text-primary hover:underline"
                      >
                        {sm.inchikey.slice(0, 14)}
                        {sm.commercially_available && " (avail.)"}
                      </a>
                    ))}
                    <span className="text-muted-foreground">&rarr;</span>
                    {route.steps.map((step, j) => (
                      <span key={j} className="text-muted-foreground">
                        [{step.reaction_class || step.reaction_id.slice(0, 8)}
                        {step.yield_pct != null &&
                          `, ${step.yield_pct.toFixed(0)}%`}
                        ]
                        {j < route.steps.length - 1 && " \u2192 "}
                      </span>
                    ))}
                    <span className="text-muted-foreground">&rarr;</span>
                    <a
                      href={`/molecules/${route.target.inchikey}`}
                      className="rounded border px-2 py-1 font-mono font-medium text-primary hover:underline"
                    >
                      {route.target.inchikey.slice(0, 14)}
                    </a>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
