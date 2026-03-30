"use client";

import { useState, useCallback, type FormEvent } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Loader2 } from "lucide-react";

interface QueryBarProps {
  onSubmit: (question: string) => void;
  isLoading?: boolean;
  value?: string;
  onChange?: (value: string) => void;
}

export function QueryBar({ onSubmit, isLoading, value, onChange }: QueryBarProps) {
  const [localValue, setLocalValue] = useState("");
  const question = value ?? localValue;
  const setQuestion = onChange ?? setLocalValue;

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      const trimmed = question.trim();
      if (trimmed.length >= 3) {
        onSubmit(trimmed);
      }
    },
    [question, onSubmit],
  );

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="text"
          placeholder="Ask a chemistry question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          className="pl-9"
          disabled={isLoading}
        />
      </div>
      <Button type="submit" disabled={isLoading || question.trim().length < 3}>
        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          "Search"
        )}
      </Button>
    </form>
  );
}
