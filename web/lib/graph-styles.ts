import type { StylesheetStyle } from "cytoscape";

export const GRAPH_STYLESHEET: StylesheetStyle[] = [
  {
    selector: "node[type='molecule']",
    style: {
      shape: "ellipse",
      width: 50,
      height: 50,
      "background-color": "#ede4f7",
      "border-color": "#6d28d9",
      "border-width": 2,
      label: "data(label)",
      "font-size": "9px",
      "text-wrap": "ellipsis" as const,
      "text-max-width": "60px",
      "text-valign": "bottom",
      "text-margin-y": 4,
      color: "#3f3f46",
    },
  },
  {
    selector: "node[type='molecule'][?commercially_available]",
    style: {
      "border-color": "#0d9488",
      "border-width": 3,
    },
  },
  {
    selector: "node[type='reaction']",
    style: {
      shape: "diamond",
      width: 30,
      height: 30,
      "background-color": "#fef3c7",
      "border-color": "#f59e0b",
      "border-width": 1.5,
      label: "data(label)",
      "font-size": "8px",
      "text-valign": "bottom",
      "text-margin-y": 3,
      color: "#71717a",
    },
  },
  {
    selector: "edge[type='REACTANT_IN']",
    style: {
      "line-color": "#6d28d9",
      "target-arrow-color": "#6d28d9",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      width: 1.5,
    },
  },
  {
    selector: "edge[type='PRODUCT_OF']",
    style: {
      "line-color": "#0d9488",
      "target-arrow-color": "#0d9488",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      width: 1.5,
    },
  },
  {
    selector: "edge[type='PRECURSOR_OF']",
    style: {
      "line-color": "#7c3aed",
      "target-arrow-color": "#7c3aed",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      width: 1.5,
      "line-style": "dashed",
    },
  },
  {
    selector: "edge[type='SIMILAR_TO']",
    style: {
      "line-color": "#d6d3d1",
      "target-arrow-shape": "none",
      "curve-style": "bezier",
      width: 1,
      "line-style": "dotted",
    },
  },
  {
    selector: "node:selected",
    style: {
      "border-color": "#5b21b6",
      "border-width": 3,
      "background-color": "#ddd6fe",
    },
  },
];
