"use client";

import { useCallback, useRef, useMemo } from "react";
import type { Core, ElementDefinition } from "cytoscape";
import CytoscapeComponent from "react-cytoscapejs";
import { GRAPH_STYLESHEET } from "@/lib/graph-styles";
import type { RouteSearchResult } from "@/lib/api-types";

interface GraphExplorerProps {
  data: RouteSearchResult;
  onNodeSelect?: (inchikey: string) => void;
  onCyInit?: (cy: Core) => void;
}

function routesToElements(data: RouteSearchResult): ElementDefinition[] {
  const nodes = new Map<string, ElementDefinition>();
  const edges: ElementDefinition[] = [];

  for (const route of data.routes) {
    // Target molecule
    const t = route.target;
    if (!nodes.has(t.inchikey)) {
      nodes.set(t.inchikey, {
        data: {
          id: t.inchikey,
          label: t.inchikey.slice(0, 10),
          type: "molecule",
          commercially_available: t.commercially_available,
        },
      });
    }

    // Starting materials
    for (const sm of route.starting_materials) {
      if (!nodes.has(sm.inchikey)) {
        nodes.set(sm.inchikey, {
          data: {
            id: sm.inchikey,
            label: sm.inchikey.slice(0, 10),
            type: "molecule",
            commercially_available: sm.commercially_available,
          },
        });
      }
    }

    // Reaction steps
    for (const step of route.steps) {
      const rxnId = `rxn-${step.reaction_id}`;
      if (!nodes.has(rxnId)) {
        nodes.set(rxnId, {
          data: {
            id: rxnId,
            label: step.reaction_class
              ? step.reaction_class.slice(0, 12)
              : step.reaction_id.slice(0, 8),
            type: "reaction",
            yield_pct: step.yield_pct,
          },
        });
      }
    }

    // Connect starting materials -> first reaction -> ... -> target
    // For simple routes: SM -> rxn -> target
    if (route.steps.length === 1 && route.starting_materials.length > 0) {
      const rxnId = `rxn-${route.steps[0].reaction_id}`;
      for (const sm of route.starting_materials) {
        const edgeId = `${sm.inchikey}->${rxnId}`;
        edges.push({
          data: {
            id: edgeId,
            source: sm.inchikey,
            target: rxnId,
            type: "REACTANT_IN",
          },
        });
      }
      edges.push({
        data: {
          id: `${rxnId}->${t.inchikey}`,
          source: rxnId,
          target: t.inchikey,
          type: "PRODUCT_OF",
        },
      });
    } else if (route.steps.length > 1) {
      // Multi-step: connect sequentially
      for (let i = 0; i < route.steps.length; i++) {
        const rxnId = `rxn-${route.steps[i].reaction_id}`;
        if (i === 0) {
          for (const sm of route.starting_materials) {
            edges.push({
              data: {
                id: `${sm.inchikey}->${rxnId}`,
                source: sm.inchikey,
                target: rxnId,
                type: "REACTANT_IN",
              },
            });
          }
        }
        if (i < route.steps.length - 1) {
          const nextRxnId = `rxn-${route.steps[i + 1].reaction_id}`;
          edges.push({
            data: {
              id: `${rxnId}->${nextRxnId}`,
              source: rxnId,
              target: nextRxnId,
              type: "PRECURSOR_OF",
            },
          });
        }
        if (i === route.steps.length - 1) {
          edges.push({
            data: {
              id: `${rxnId}->${t.inchikey}`,
              source: rxnId,
              target: t.inchikey,
              type: "PRODUCT_OF",
            },
          });
        }
      }
    }
  }

  // Deduplicate edges by id
  const uniqueEdges = new Map<string, ElementDefinition>();
  for (const e of edges) {
    uniqueEdges.set(e.data.id as string, e);
  }

  return [...nodes.values(), ...uniqueEdges.values()];
}

export function GraphExplorer({ data, onNodeSelect, onCyInit }: GraphExplorerProps) {
  const cyRef = useRef<Core | null>(null);

  const elements = useMemo(() => routesToElements(data), [data]);

  const handleCyReady = useCallback(
    (cy: Core) => {
      cyRef.current = cy;
      onCyInit?.(cy);

      cy.on("tap", "node[type='molecule']", (evt) => {
        const nodeId = evt.target.id();
        onNodeSelect?.(nodeId);
      });

      cy.layout({
        name: "breadthfirst",
        directed: true,
        spacingFactor: 1.5,
        animate: true,
        animationDuration: 300,
      }).run();
    },
    [onNodeSelect, onCyInit],
  );

  if (elements.length === 0) {
    return (
      <div className="flex h-[500px] items-center justify-center text-sm text-muted-foreground">
        No routes to display. Search for a molecule to explore its synthesis graph.
      </div>
    );
  }

  return (
    <CytoscapeComponent
      elements={elements}
      stylesheet={GRAPH_STYLESHEET}
      style={{ width: "100%", height: "500px" }}
      cy={(cy) => handleCyReady(cy)}
      boxSelectionEnabled={false}
    />
  );
}
