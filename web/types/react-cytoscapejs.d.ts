declare module "react-cytoscapejs" {
  import type { Core, ElementDefinition, StylesheetStyle } from "cytoscape";
  import type { ComponentType, CSSProperties } from "react";

  interface CytoscapeComponentProps {
    elements: ElementDefinition[];
    stylesheet?: StylesheetStyle[];
    style?: CSSProperties;
    cy?: (cy: Core) => void;
    layout?: { name: string; [key: string]: unknown };
    boxSelectionEnabled?: boolean;
    autoungrabify?: boolean;
    autounselectify?: boolean;
    pan?: { x: number; y: number };
    zoom?: number;
    minZoom?: number;
    maxZoom?: number;
    className?: string;
    id?: string;
  }

  const CytoscapeComponent: ComponentType<CytoscapeComponentProps>;
  export default CytoscapeComponent;
}
