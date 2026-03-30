"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

interface GraphControlsProps {
  maxDepth: number;
  onMaxDepthChange: (depth: number) => void;
  maxRoutes: number;
  onMaxRoutesChange: (routes: number) => void;
  onFitView: () => void;
  routeCount: number;
}

const DEPTH_OPTIONS = [2, 4, 6, 8, 12, 16];

export function GraphControls({
  maxDepth,
  onMaxDepthChange,
  maxRoutes,
  onMaxRoutesChange,
  onFitView,
  routeCount,
}: GraphControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-1.5">
        <span className="text-sm text-muted-foreground">Depth:</span>
        {DEPTH_OPTIONS.map((d) => (
          <Button
            key={d}
            size="sm"
            variant={maxDepth === d ? "default" : "outline"}
            className="h-7 w-8 px-0 text-xs"
            onClick={() => onMaxDepthChange(d)}
          >
            {d}
          </Button>
        ))}
      </div>

      <div className="flex items-center gap-1.5">
        <span className="text-sm text-muted-foreground">Max routes:</span>
        <Input
          type="number"
          min={1}
          max={50}
          value={maxRoutes}
          onChange={(e) => onMaxRoutesChange(Number(e.target.value))}
          className="h-7 w-16 text-xs"
        />
      </div>

      <Button size="sm" variant="outline" className="h-7" onClick={onFitView}>
        Fit View
      </Button>

      {routeCount > 0 && (
        <Badge variant="secondary" className="text-xs">
          {routeCount} route{routeCount !== 1 ? "s" : ""} found
        </Badge>
      )}
    </div>
  );
}
