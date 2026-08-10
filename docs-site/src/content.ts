import type { L } from "./i18n";

import ui from "../content/ui.json";
import nodes from "../content/nodes.json";
import edges from "../content/edges.json";
import ownership from "../content/ownership.json";
import phases from "../content/phases.json";
import components from "../content/components.json";
import machines from "../content/machines.json";

/** A citation as the JSON hands it over.
 *
 *  `kind` is a plain string rather than a union: TypeScript widens it when the
 *  file is imported, and narrowing it back with a cast would only move the
 *  check out of the type system into a lie. The invariants — that `code`
 *  matches the file verbatim, that `anchor` sits inside the range — are held
 *  by the Python guards, which check the actual bytes rather than a type. */
export interface Citation {
  kind: string; file: string; from: number; to: number;
  code?: string; anchor?: string;
}

export interface DetailFunction {
  name: string; decl: string; file: string; line: number; note: L;
}

export interface FlowStep { id: string; label: L }
export interface FlowEdge { from: string; to: string; label?: L }

export interface ComponentDetail {
  id: string;
  functions: DetailFunction[];
  flow?: {
    nodes: FlowStep[]; edges: FlowEdge[];
    gates: FlowStep[]; exits: FlowStep[];
  };
  excerpts: { caption: L; cite: Citation }[];
  why: { text: L; cite: Citation }[];
  debts: { text: L; cite: Citation }[];
}

// The 21 detail files, keyed by component id. Globbed rather than imported one
// by one so adding a component is a content change, not a code change — which
// is the whole premise of the guards.
const details = import.meta.glob("../content/components/*.json",
                                 { eager: true, import: "default" });

export const componentDetails: Record<string, ComponentDetail> =
  Object.fromEntries(Object.entries(details).map(([path, value]) =>
    [path.split("/").pop()!.replace(/\.json$/, ""), value as ComponentDetail]));

export const content = {
  ui, nodes, edges, ownership, phases, components, machines, componentDetails,
};

export type Component = (typeof components)["components"][number];
export type MapNode = (typeof nodes)["nodes"][number];
export type MapEdge = (typeof edges)["edges"][number];
