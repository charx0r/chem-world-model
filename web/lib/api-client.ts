import type {
  GraphStats,
  MoleculeDetail,
  MoleculeSearchParams,
  MoleculeSearchResult,
  QueryResult,
  ReactionDetail,
  ReactionSearchParams,
  ReactionSearchResult,
  RouteSearchResult,
} from "./api-types";

function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  // Server Components need an absolute URL — browser can use relative paths
  if (typeof window === "undefined") return "http://api:8000";
  return "";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetcher<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json();
}

function toSearchParams(params: object): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)]));
}

export const api = {
  health: () => fetcher<{ status: string }>("/health"),

  query: (question: string) =>
    fetcher<QueryResult>("/api/query", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  browseMolecules: (params: { q?: string; limit?: number; offset?: number }) =>
    fetcher<MoleculeSearchResult>(
      `/api/molecules/browse${toSearchParams(params)}`,
    ),

  browseReactions: (params: { q?: string; limit?: number; offset?: number }) =>
    fetcher<ReactionSearchResult>(
      `/api/reactions/browse${toSearchParams(params)}`,
    ),

  getMolecule: (inchikey: string) =>
    fetcher<MoleculeDetail>(`/api/molecules/${inchikey}`),

  searchMolecules: (params: MoleculeSearchParams) =>
    fetcher<MoleculeSearchResult>(
      `/api/molecules/search${toSearchParams(params)}`,
    ),

  getReaction: (id: string) => fetcher<ReactionDetail>(`/api/reactions/${id}`),

  searchReactions: (params: ReactionSearchParams) =>
    fetcher<ReactionSearchResult>(
      `/api/reactions/search${toSearchParams(params)}`,
    ),

  getRoutes: (inchikey: string, maxDepth = 8, maxRoutes = 10) =>
    fetcher<RouteSearchResult>(
      `/api/graph/routes/${inchikey}?max_depth=${maxDepth}&max_routes=${maxRoutes}`,
    ),

  getGraphStats: () => fetcher<GraphStats>("/api/graph/stats"),
};
