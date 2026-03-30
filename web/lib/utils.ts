import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format a number with locale separators (e.g. 1,234,567) */
export function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

/** Format seconds into a human-readable duration */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}min`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}min` : `${h}h`;
}

/** Format temperature with unit */
export function formatTemp(celsius: number | null): string {
  if (celsius === null) return "\u2014";
  return `${celsius}\u00b0C`;
}

/** Format yield percentage with color hint */
export function yieldColor(pct: number | null): string {
  if (pct === null) return "text-muted-foreground";
  if (pct >= 80) return "text-teal-600";
  if (pct >= 50) return "text-amber-600";
  return "text-rose-600";
}

/** Truncate a SMILES string for display */
export function truncateSmiles(smiles: string, maxLen = 40): string {
  if (smiles.length <= maxLen) return smiles;
  return smiles.slice(0, maxLen - 1) + "\u2026";
}
