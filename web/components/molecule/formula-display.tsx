import { cn } from "@/lib/utils";

interface FormulaDisplayProps {
  formula: string;
  className?: string;
}

/**
 * Renders a molecular formula with proper subscript numbers.
 * E.g., "C9H8O4" → C<sub>9</sub>H<sub>8</sub>O<sub>4</sub>
 * Handles charges like "H-", "Na+", "SO4 2-" as superscripts.
 */
export function FormulaDisplay({ formula, className }: FormulaDisplayProps) {
  // Split formula into tokens: letter groups, digit groups, charges (+/-)
  const tokens = formula.match(/[A-Za-z]+|\d+|[+\-]+/g);
  if (!tokens) return <span className={className}>{formula}</span>;

  return (
    <span className={cn("", className)}>
      {tokens.map((token, i) => {
        if (/^\d+$/.test(token)) {
          return <sub key={i}>{token}</sub>;
        }
        if (/^[+\-]+$/.test(token)) {
          return <sup key={i}>{token}</sup>;
        }
        return <span key={i}>{token}</span>;
      })}
    </span>
  );
}
