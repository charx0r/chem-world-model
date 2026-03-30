import { Badge } from "@/components/ui/badge";
import { formatTemp, formatDuration, yieldColor } from "@/lib/utils";
import type { ReactionDetail } from "@/lib/api-types";

interface ConditionsTableProps {
  reaction: ReactionDetail;
}

export function ConditionsTable({ reaction }: ConditionsTableProps) {
  return (
    <div className="flex flex-wrap gap-3">
      {reaction.yield_pct != null && (
        <div className="text-center">
          <p className="text-xs text-muted-foreground">Yield</p>
          <p className={`font-mono text-lg font-semibold ${yieldColor(reaction.yield_pct)}`}>
            {reaction.yield_pct.toFixed(1)}%
          </p>
          {reaction.yield_type && (
            <p className="text-[10px] text-muted-foreground">
              {reaction.yield_type}
            </p>
          )}
        </div>
      )}
      {reaction.temperature_c != null && (
        <div className="text-center">
          <p className="text-xs text-muted-foreground">Temperature</p>
          <p className="font-mono text-sm">{formatTemp(reaction.temperature_c)}</p>
        </div>
      )}
      {reaction.pressure_bar != null && (
        <div className="text-center">
          <p className="text-xs text-muted-foreground">Pressure</p>
          <p className="font-mono text-sm">{reaction.pressure_bar} bar</p>
        </div>
      )}
      {reaction.time_seconds != null && (
        <div className="text-center">
          <p className="text-xs text-muted-foreground">Time</p>
          <p className="font-mono text-sm">
            {formatDuration(reaction.time_seconds)}
          </p>
        </div>
      )}
      {reaction.atmosphere && (
        <div className="text-center">
          <p className="text-xs text-muted-foreground">Atmosphere</p>
          <Badge variant="secondary" className="text-xs">
            {reaction.atmosphere}
          </Badge>
        </div>
      )}
      {reaction.selectivity && (
        <div className="text-center">
          <p className="text-xs text-muted-foreground">Selectivity</p>
          <p className="text-sm">{reaction.selectivity}</p>
        </div>
      )}
    </div>
  );
}
