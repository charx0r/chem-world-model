import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { HazardInfo } from "@/lib/api-types";

interface HazardBadgesProps {
  hazards: HazardInfo[];
}

export function HazardBadges({ hazards }: HazardBadgesProps) {
  if (hazards.length === 0) return null;

  const allCodes = hazards.flatMap((h) => h.ghs_codes);
  const signalWord = hazards.find((h) => h.signal_word)?.signal_word;
  const allPictograms = [...new Set(hazards.flatMap((h) => h.pictograms))];

  return (
    <div className="space-y-2">
      {signalWord && (
        <Badge
          variant={signalWord === "Danger" ? "destructive" : "secondary"}
          className="text-xs"
        >
          {signalWord}
        </Badge>
      )}
      {allPictograms.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {allPictograms.map((p) => (
            <Tooltip key={p}>
              <TooltipTrigger className="cursor-default">
                <Badge variant="outline" className="text-xs">
                  {p}
                </Badge>
              </TooltipTrigger>
              <TooltipContent>{p}</TooltipContent>
            </Tooltip>
          ))}
        </div>
      )}
      {allCodes.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {allCodes.map((code) => (
            <Badge key={code} variant="outline" className="font-mono text-xs">
              {code}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
