import { content, type MapEdge } from "../content";
import { pick } from "../i18n";
import type { Lang, Route } from "../route";
import {
  BOX_PADDING, LABEL_CHARS, LANE_PITCH, LINE_HEIGHT,
  columnGap, laneOffsets, nodeHeight, wrapLabel,
} from "../svg/layout";
import { ContractPanel } from "./ContractPanel";
import { DiagramText, type TextSection } from "./DiagramText";
import { OwnershipTable } from "./OwnershipTable";

const NODE_WIDTH = 168;
const ROW_GAP = 28;
const MARGIN = 24;

type Placed = {
  id: string; column: number; x: number; y: number; h: number;
  label: { vi: string; en: string }; summary: { vi: string; en: string };
  kind: string;
};

/** Which gap a given edge turns in.
 *
 *  A gap holds one lane per edge crossing it, and gaps do not overlap, so
 *  every edge in the diagram ends up with a turn line of its own. Two edges
 *  sharing a path — or sharing a label position — is the failure this
 *  arithmetic exists to prevent. */
const gapOf = (from: Placed, to: Placed): number =>
  from.column === to.column ? from.column : Math.max(from.column, to.column) - 1;

function layout(lang: Lang) {
  const nodes = content.nodes.nodes;
  const byColumn = new Map<number, typeof nodes>();
  nodes.forEach((node) => {
    byColumn.set(node.column, [...(byColumn.get(node.column) ?? []), node]);
  });

  // Lane counts first: a column's x depends on how many lines cross the gap
  // before it, so the gaps are measured before anything is placed.
  const columnOf = new Map(nodes.map((n) => [n.id, n.column]));
  const laneCount = new Map<number, number>();
  content.edges.edges.forEach((edge) => {
    const a = columnOf.get(edge.from)!;
    const b = columnOf.get(edge.to)!;
    const gap = a === b ? a : Math.max(a, b) - 1;
    laneCount.set(gap, (laneCount.get(gap) ?? 0) + 1);
  });

  const columns = [...byColumn.keys()].sort((a, b) => a - b);
  const columnX = new Map<number, number>();
  let x = MARGIN;
  columns.forEach((column) => {
    columnX.set(column, x);
    x += NODE_WIDTH + columnGap(laneCount.get(column) ?? 1);
  });

  const placed: Placed[] = [];
  columns.forEach((column) => {
    let y = MARGIN;
    (byColumn.get(column) ?? []).forEach((node) => {
      const h = nodeHeight(node);
      placed.push({
        id: node.id, column, x: columnX.get(column)!, y, h,
        label: node.label, summary: node.summary, kind: node.kind,
      });
      y += h + ROW_GAP;
    });
  });

  const byId = new Map(placed.map((p) => [p.id, p]));

  // One lane counter per gap, shared by every edge that turns in it.
  const nextLane = new Map<number, number>();
  const lanes = new Map<number, number[]>();
  laneCount.forEach((count, gap) => lanes.set(gap, laneOffsets(count)));

  const routed = content.edges.edges.map((edge) => {
    const from = byId.get(edge.from)!;
    const to = byId.get(edge.to)!;
    const gap = gapOf(from, to);
    const index = nextLane.get(gap) ?? 0;
    nextLane.set(gap, index + 1);
    const offset = lanes.get(gap)![index];

    const gapStart = columnX.get(gap)! + NODE_WIDTH;
    const gapWidth = columnGap(laneCount.get(gap) ?? 1);
    const turnX = gapStart + gapWidth / 2 + offset;

    const y1 = from.y + from.h / 2;
    const y2 = to.y + to.h / 2;
    const startX = from.x + NODE_WIDTH;
    const endX = from.column === to.column ? to.x + NODE_WIDTH : to.x;

    return {
      edge, turnX,
      d: `M ${startX} ${y1} H ${turnX} V ${y2} H ${endX}`,
      // The midpoint of the TURN segment, never the source box centre: two
      // edges leaving the same node in different directions would otherwise
      // be handed the same coordinate.
      labelX: turnX, labelY: (y1 + y2) / 2,
    };
  });

  const width = x + MARGIN;
  const height = Math.max(
    ...placed.map((p) => p.y + p.h), MARGIN) + MARGIN;

  return { placed, routed, width, height, lang };
}

function NodeShape({ node, lang }: { node: Placed; lang: Lang }) {
  const lines = wrapLabel(pick(node.label, lang), LABEL_CHARS);
  const top = node.y + BOX_PADDING + LINE_HEIGHT * 0.8;
  return (
    <g role="img" aria-label={pick(node.label, lang)} data-node={node.id}>
      <rect
        className={`node node-${node.kind}`}
        x={node.x} y={node.y} width={NODE_WIDTH} height={node.h} rx={10}
      />
      <text className="node-label" x={node.x + NODE_WIDTH / 2} textAnchor="middle">
        {lines.map((line, i) => (
          <tspan key={i} x={node.x + NODE_WIDTH / 2} y={top + i * LINE_HEIGHT}>
            {line}
          </tspan>
        ))}
      </text>
    </g>
  );
}

function textSections(lang: Lang): TextSection[] {
  const label = (id: string) => {
    const node = content.nodes.nodes.find((n) => n.id === id)!;
    return pick(node.label, lang);
  };
  return [
    {
      heading: content.ui.nav.map,
      entries: content.nodes.nodes.map((node) => ({
        label: node.label, detail: node.summary,
      })),
    },
    {
      heading: content.ui.aria.systemMap,
      entries: content.edges.edges.map((edge) => ({
        label: edge.label,
        detail: {
          vi: `${label(edge.from)} → ${label(edge.to)}: ${edge.summary.vi}`,
          en: `${label(edge.from)} -> ${label(edge.to)}: ${edge.summary.en}`,
        },
      })),
    },
  ];
}

export function SystemMap(
  { lang, phase, route, go }: {
    lang: Lang; phase: string | null;
    route?: Route; go?: (next: Route) => void;
  },
) {
  const { placed, routed, width, height } = layout(lang);
  const open: MapEdge | undefined = route?.sub?.kind === "edge"
    ? content.edges.edges.find((e) => e.id === route.sub!.id)
    : undefined;

  const openEdge = (edge: MapEdge) => {
    if (!route || !go) return;
    go({ ...route, sub: { kind: "edge", id: edge.id } });
  };

  return (
    <div className="layer layer-map">
      <div className="scroll-x">
        <svg
          className="map"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="group"
          aria-label={pick(content.ui.aria.systemMap, lang)}
        >
          {routed.map(({ edge, d, labelX, labelY }) => (
            <g
              key={edge.id}
              role="button"
              tabIndex={0}
              aria-label={pick(edge.label, lang)}
              className={`edge${open?.id === edge.id ? " edge-open" : ""}`}
              onClick={() => openEdge(edge)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  openEdge(edge);
                }
              }}
            >
              <path className="edge-hit" data-edge-hit={edge.id} d={d} />
              <path className="edge-line" data-edge={edge.id} d={d} />
              <text
                className="edge-label"
                data-edge-label={edge.id}
                x={labelX} y={labelY} textAnchor="middle"
              >
                {pick(edge.label, lang)}
              </text>
            </g>
          ))}
          {placed.map((node) => (
            <NodeShape key={node.id} node={node} lang={lang} />
          ))}
        </svg>
      </div>

      <DiagramText sections={textSections(lang)} lang={lang} />

      {open ? <ContractPanel edge={open} lang={lang} route={route} go={go} /> : null}

      <OwnershipTable lang={lang} phase={phase} />
    </div>
  );
}

export const MAP_CONSTANTS = { NODE_WIDTH, LANE_PITCH };
