"use client";

import { Badge } from "@/components/ui/badge";

const EXAMPLES = [
  "What reactions produce aspirin?",
  "Find molecules with LogP > 5 and MW < 500",
  "Show Suzuki coupling reactions with yield above 80%",
  "Which solvents are most common in amide bond formations?",
  "Find commercially available precursors for ibuprofen",
  "List reactions run under nitrogen atmosphere above 100\u00b0C",
];

interface ExampleQuestionsProps {
  onSelect: (question: string) => void;
}

export function ExampleQuestions({ onSelect }: ExampleQuestionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {EXAMPLES.map((q) => (
        <Badge
          key={q}
          variant="secondary"
          className="cursor-pointer transition-colors hover:bg-primary/10 hover:text-primary"
          onClick={() => onSelect(q)}
        >
          {q}
        </Badge>
      ))}
    </div>
  );
}
