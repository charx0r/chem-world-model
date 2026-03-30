"use client";

import { useState, useCallback, useEffect } from "react";
import { QueryBar } from "@/components/query/query-bar";
import { ExampleQuestions } from "@/components/query/example-questions";
import { QueryResults } from "@/components/query/query-results";
import { Separator } from "@/components/ui/separator";
import { api, ApiError } from "@/lib/api-client";
import { formatNumber } from "@/lib/utils";
import type { QueryResult, GraphStats } from "@/lib/api-types";

export default function HomePage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<GraphStats | null>(null);

  useEffect(() => {
    api.getGraphStats().then(setStats).catch(() => {});
  }, []);

  const handleQuery = useCallback(async (q: string) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.query(q);
      setResult(res);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError("Failed to connect to the API. Is the server running?");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const handleExampleSelect = useCallback(
    (q: string) => {
      setQuestion(q);
      handleQuery(q);
    },
    [handleQuery],
  );

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* Header section */}
      <div className="mb-8 text-center">
        <h1 className="mb-2 font-serif text-3xl font-semibold tracking-tight">
          ChemWorldModel
        </h1>
        <p className="text-muted-foreground">
          Query chemical reactions, explore molecules, and plan synthesis routes
          using natural language.
        </p>
        <div className="mt-3 flex h-5 items-center justify-center gap-4 text-sm text-muted-foreground">
          {stats && (
            <>
              <span>{formatNumber(stats.molecule_count)} molecules</span>
              <span className="text-border">|</span>
              <span>{formatNumber(stats.reaction_count)} reactions</span>
              {Object.entries(stats.edge_counts).map(([type, count]) => (
                <span key={type} className="hidden sm:inline">
                  <span className="text-border">|</span>{" "}
                  {formatNumber(count)} {type.toLowerCase().replace(/_/g, " ")}{" "}
                  edges
                </span>
              ))}
            </>
          )}
        </div>
      </div>

      {/* Query bar */}
      <div className="mb-4">
        <QueryBar
          value={question}
          onChange={setQuestion}
          onSubmit={handleQuery}
          isLoading={loading}
        />
      </div>

      {/* Example questions — always visible unless loading */}
      {!loading && (
        <div className={`mb-6 ${result || error ? "opacity-60" : ""}`}>
          <p className="mb-2 text-sm text-muted-foreground">
            {result || error ? "Try another:" : "Try an example:"}
          </p>
          <ExampleQuestions onSelect={handleExampleSelect} />
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-start justify-between rounded-lg border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="ml-2 shrink-0 text-destructive/70 hover:text-destructive"
          >
            &times;
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <p className="text-sm text-muted-foreground">
              Analyzing your question...
            </p>
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <>
          <Separator className="my-6" />
          <QueryResults result={result} />
        </>
      )}
    </div>
  );
}
