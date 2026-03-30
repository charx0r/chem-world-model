import { Badge } from "@/components/ui/badge";
import type { ReactionDetail } from "@/lib/api-types";

interface ProvenanceLinkProps {
  reaction: ReactionDetail;
}

export function ProvenanceLink({ reaction }: ProvenanceLinkProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {reaction.source && (
        <Badge variant="secondary" className="text-xs">
          {reaction.source}
        </Badge>
      )}
      {reaction.source_id && (
        <span className="font-mono text-xs text-muted-foreground">
          {reaction.source_id}
        </span>
      )}
      {reaction.doi && (
        <a
          href={`https://doi.org/${reaction.doi}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-primary hover:underline"
        >
          DOI: {reaction.doi}
        </a>
      )}
      {reaction.patent_id && (
        <a
          href={`https://patents.google.com/patent/${reaction.patent_id}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-primary hover:underline"
        >
          Patent: {reaction.patent_id}
        </a>
      )}
    </div>
  );
}
