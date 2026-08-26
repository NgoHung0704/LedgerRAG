import { useMemo, useState } from "react";
import { content } from "../content";
import { pick } from "../i18n";
import type { Lang, Route } from "../route";
import {
  BOX_PADDING, LABEL_CHARS, LINE_HEIGHT,
  columnGap, laneOffsets, nodeHeight, wirePath, wrapLabel,
} from "../svg/layout";
import { ContractPanel } from "./ContractPanel";
import { DiagramText, type TextSection } from "./DiagramText";
import { OwnershipTable } from "./OwnershipTable";

const NODE_WIDTH = 168;
const ROW_GAP = 26;
const MARGIN = 24;
const HEADER = 40;

type MapNode = (typeof content.nodes.nodes)[number];
type MapEdge = (typeof content.edges.edges)[number];

interface Placed extends MapNode { x: number; y: number; h: number }

/** A wire, not one arrow per contract.
 *
 *  Nine contract families run between the frontend and the API. Drawn as nine
 *  labelled arrows they became an unreadable smear; drawn as ONE wire carrying
 *  a count, the board reads like a board. The families are not hidden - they
 *  are one click away, and the text version still lists every one of them. */
interface Wire {
  id: string; from: string; to: string; edges: MapEdge[];
  d: string; midX: number; midY: number;
}

const COLUMN_KEYS = ["external", "services", "stores", "models"] as const;

function useBoard(lang: Lang) {
  return useMemo(() => {
    const nodes = content.nodes.nodes;
    const columnOf = new Map(nodes.map((n) => [n.id, n.column]));

    const grouped = new Map<string, MapEdge[]>();
    content.edges.edges.forEach((edge) => {
      const key = `${edge.from}~${edge.to}`;
      grouped.set(key, [...(grouped.get(key) ?? []), edge]);
    });

    // A wire turns in the gap after the leftmost of its two columns; a wire
    // between two nodes of the SAME column loops out to the right of it.
    const gapOf = (from: string, to: string) => {
      const a = columnOf.get(from)!;
      const b = columnOf.get(to)!;
      return a === b ? a : Math.max(a, b) - 1;
    };

    const laneCount = new Map<number, number>();
    [...grouped.keys()].forEach((key) => {
      const [from, to] = key.split("~");
      const gap = gapOf(from, to);
      laneCount.set(gap, (laneCount.get(gap) ?? 0) + 1);
    });

    const columns = [...new Set(nodes.map((n) => n.column))].sort((a, b) => a - b);
    const columnX = new Map<number, number>();
    let x = MARGIN;
    columns.forEach((column) => {
      columnX.set(column, x);
      x += NODE_WIDTH + columnGap(laneCount.get(column) ?? 1);
    });
    const width = columnX.get(columns[columns.length - 1])! + NODE_WIDTH + MARGIN;

    // Every column is centred against the tallest, so the board sits level
    // instead of hanging off the top edge.
    const stackHeight = new Map<number, number>();
    columns.forEach((column) => {
      const own = nodes.filter((n) => n.column === column);
      stackHeight.set(column, own.reduce((sum, n) => sum + nodeHeight(n), 0)
        + ROW_GAP * (own.length - 1));
    });
    const tallest = Math.max(...stackHeight.values());

    const placed: Placed[] = [];
    columns.forEach((column) => {
      let y = MARGIN + HEADER + (tallest - stackHeight.get(column)!) / 2;
      nodes.filter((n) => n.column === column).forEach((node) => {
        const h = nodeHeight(node);
        placed.push({ ...node, x: columnX.get(column)!, y, h });
        y += h + ROW_GAP;
      });
    });
    const byId = new Map(placed.map((p) => [p.id, p]));

    const lanes = new Map<number, number[]>();
    laneCount.forEach((count, gap) => lanes.set(gap, laneOffsets(count)));
    const nextLane = new Map<number, number>();

    const wires: Wire[] = [...grouped.entries()].map(([id, edges]) => {
      const [fromId, toId] = id.split("~");
      const from = byId.get(fromId)!;
      const to = byId.get(toId)!;
      const gap = gapOf(fromId, toId);
      const index = nextLane.get(gap) ?? 0;
      nextLane.set(gap, index + 1);

      const gapStart = columnX.get(gap)! + NODE_WIDTH;
      const turnX = gapStart + columnGap(laneCount.get(gap) ?? 1) / 2
        + lanes.get(gap)![index];
      const y1 = from.y + from.h / 2;
      const y2 = to.y + to.h / 2;
      const sameColumn = from.column === to.column;

      return {
        id, from: fromId, to: toId, edges,
        d: wirePath(from.x + NODE_WIDTH, y1, turnX,
                    sameColumn ? to.x + NODE_WIDTH : to.x, y2),
        // The middle of the wire's OWN turn, never the source box: two wires
        // leaving one node in different directions would share that point.
        midX: turnX, midY: (y1 + y2) / 2,
      };
    });

    return {
      placed, wires, columns, columnX, width,
      height: MARGIN * 2 + HEADER + tallest,
    };
  }, [lang]);
}

function textSections(lang: Lang): TextSection[] {
  const label = (id: string) =>
    pick(content.nodes.nodes.find((n) => n.id === id)!.label, lang);
  return [
    {
      heading: content.ui.headings.modules,
      entries: content.nodes.nodes.map((node) => ({
        label: node.label, detail: node.summary,
      })),
    },
    {
      heading: content.ui.headings.wires,
      entries: content.edges.edges.map((edge) => ({
        label: edge.label,
        detail: {
          vi: `${label(edge.from)} → ${label(edge.to)}: ${edge.summary.vi}`,
          en: `${label(edge.from)} -> ${label(edge.to)}: ${edge.summary.en}`,
          fr: `${label(edge.from)} -> ${label(edge.to)} : ${edge.summary.fr}`,
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
  const board = useBoard(lang);
  const [hovered, setHovered] = useState<string | null>(null);
  const selected = route?.sub?.kind === "edge" ? route.sub.id : null;
  const active = hovered ?? selected;
  const activeWire = board.wires.find((w) => w.id === active) ?? null;
  const openWire = board.wires.find((w) => w.id === selected) ?? null;

  const lit = (id: string) =>
    !activeWire || activeWire.from === id || activeWire.to === id;

  const toggle = (wire: Wire) => {
    if (!route || !go) return;
    go({ ...route, sub: selected === wire.id ? null : { kind: "edge", id: wire.id } });
  };

  return (
    <div className="layer layer-map">
      <div className="scroll-x">
        <div
          className={`board${activeWire ? " board-spotlight" : ""}`}
          style={{ width: board.width, height: board.height }}
        >
          <svg
            className="map"
            width={board.width}
            height={board.height}
            viewBox={`0 0 ${board.width} ${board.height}`}
            role="group"
            aria-label={pick(content.ui.aria.systemMap, lang)}
          >
            <defs>
              <marker
                id="tip" viewBox="0 0 8 8" refX="6.5" refY="4"
                markerWidth="6" markerHeight="6" orient="auto-start-reverse"
              >
                <path className="tip" d="M 0 1 L 6.5 4 L 0 7 z" />
              </marker>
            </defs>

            {board.columns.map((column, i) => (
              <text
                key={column}
                className="stage"
                x={board.columnX.get(column)! + NODE_WIDTH / 2}
                y={MARGIN + 14}
                textAnchor="middle"
              >
                {pick(content.ui.columns[COLUMN_KEYS[i]], lang)}
              </text>
            ))}

            {board.wires.map((wire, i) => (
              <g
                key={wire.id}
                data-wire={wire.id}
                data-dim-wrapper
                className={[
                  "wire",
                  wire.id === active ? "wire-active" : "",
                  lit(wire.from) && lit(wire.to) ? "" : "dimmed",
                ].filter(Boolean).join(" ")}
                style={{ ["--i" as string]: i }}
                role="button"
                tabIndex={0}
                aria-label={pick(wire.edges[0].label, lang)}
                aria-expanded={wire.id === selected}
                onMouseEnter={() => setHovered(wire.id)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(wire.id)}
                onBlur={() => setHovered(null)}
                onClick={() => toggle(wire)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    toggle(wire);
                  }
                }}
              >
                <path className="wire-hit" d={wire.d} />
                <path
                  className="wire-line" data-wire-path={wire.id}
                  d={wire.d} pathLength={1} markerEnd="url(#tip)"
                />
                {wire.edges.length > 1 ? (
                  <g className="chip">
                    <circle cx={wire.midX} cy={wire.midY} r={10} />
                    <text x={wire.midX} y={wire.midY + 3.5} textAnchor="middle">
                      {wire.edges.length}
                    </text>
                  </g>
                ) : null}
              </g>
            ))}

            {board.placed.map((node) => (
              <g
                key={node.id}
                data-node={node.id}
                data-dim-wrapper
                className={lit(node.id) ? undefined : "dimmed"}
                role="img"
                aria-label={pick(node.label, lang)}
              >
                <rect
                  className="node" x={node.x} y={node.y}
                  width={NODE_WIDTH} height={node.h} rx={9}
                />
                <rect
                  className={`rail rail-${node.kind}`}
                  x={node.x} y={node.y + 9} width={3} height={node.h - 18} rx={1.5}
                />
                <text className="node-label" textAnchor="middle">
                  {wrapLabel(pick(node.label, lang), LABEL_CHARS).map((line, i, all) => (
                    <tspan
                      key={i}
                      x={node.x + NODE_WIDTH / 2 + 2}
                      y={node.y + (node.h - all.length * LINE_HEIGHT) / 2
                        + BOX_PADDING + i * LINE_HEIGHT}
                    >
                      {line}
                    </tspan>
                  ))}
                </text>
              </g>
            ))}
          </svg>

          {activeWire ? (
            <div
              className="wire-label"
              style={{ left: activeWire.midX, top: activeWire.midY }}
            >
              {activeWire.edges.map((edge) => (
                <span key={edge.id}>{pick(edge.label, lang)}</span>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <p className="hint">{pick(content.ui.hints.selectWire, lang)}</p>

      <DiagramText sections={textSections(lang)} lang={lang} />

      {openWire ? (
        <ContractPanel
          key={openWire.id} wire={openWire.edges}
          lang={lang} route={route} go={go}
        />
      ) : null}

      <OwnershipTable lang={lang} phase={phase} />
    </div>
  );
}
