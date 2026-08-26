import { useState } from "react";
import type { ComponentDetail } from "../content";
import { pick, type L } from "../i18n";
import type { Lang } from "../route";
import {
  BOX_PADDING, LABEL_CHARS, LINE_HEIGHT,
  columnGap, labelHeight, laneOffsets, wirePath, wrapLabel,
} from "../svg/layout";

const BOX_WIDTH = 190;
const ROW_GAP = 22;

type Kind = "step" | "gate" | "exit";
type Box = { id: string; kind: Kind; label: L; x: number; y: number; h: number };

/** Steps on the left, branch points in the middle, exits on the right - the
 *  shape a reader already expects from a pipeline drawing.
 *
 *  Branch labels are not written onto the wires. Written flat they collide;
 *  written turned they are unreadable, which is what the first version did.
 *  They appear, horizontally and in real type, for the box under the pointer
 *  or the keyboard - and the text version below carries all of them at once. */
export function FlowDiagram(
  { flow, lang }: { flow: NonNullable<ComponentDetail["flow"]>; lang: Lang },
) {
  const [active, setActive] = useState<string | null>(null);

  const COL_GAP = columnGap(flow.edges.length);
  const columns: { kind: Kind; items: { id: string; label: L }[] }[] = [
    { kind: "step", items: flow.nodes },
    { kind: "gate", items: flow.gates ?? [] },
    { kind: "exit", items: flow.exits ?? [] },
  ];

  const boxes: Box[] = [];
  let x = 16;
  columns.forEach(({ kind, items }) => {
    if (!items.length) return;
    let y = 16;
    items.forEach((item) => {
      const h = labelHeight(item.label);
      boxes.push({ id: item.id, kind, label: item.label, x, y, h });
      y += h + ROW_GAP;
    });
    x += BOX_WIDTH + COL_GAP;
  });

  const byId = new Map(boxes.map((b) => [b.id, b]));
  const offsets = laneOffsets(flow.edges.length);

  const routed = flow.edges.map((edge, i) => {
    const from = byId.get(edge.from);
    const to = byId.get(edge.to);
    if (!from || !to) return null;
    const y1 = from.y + from.h / 2;
    const y2 = to.y + to.h / 2;
    const turnX = from.x + BOX_WIDTH + COL_GAP / 2 + offsets[i];
    return {
      key: `${edge.from}-${edge.to}-${i}`, edge,
      d: wirePath(from.x + BOX_WIDTH, y1, turnX, to.x, y2),
      midX: turnX, midY: (y1 + y2) / 2,
    };
  }).filter((r): r is NonNullable<typeof r> => r !== null);

  const touches = (edge: { from: string; to: string }) =>
    active === null || edge.from === active || edge.to === active;
  const near = (id: string) => active === null || id === active
    || routed.some(({ edge }) => (edge.from === active && edge.to === id)
      || (edge.to === active && edge.from === id));

  const width = x - COL_GAP + 16;
  const height = Math.max(...boxes.map((b) => b.y + b.h), 40) + 20;
  const shown = routed.filter((r) => active !== null && touches(r.edge) && r.edge.label);

  return (
    <div className="scroll-x">
      <div
        className={`board${active ? " board-spotlight" : ""}`}
        style={{ width, height }}
      >
        <svg
          className="flow" width={width} height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="group" aria-label={pick(flow.nodes[0].label, lang)}
        >
          <defs>
            <marker
              id="flow-tip" viewBox="0 0 8 8" refX="6.5" refY="4"
              markerWidth="6" markerHeight="6" orient="auto-start-reverse"
            >
              <path className="tip" d="M 0 1 L 6.5 4 L 0 7 z" />
            </marker>
          </defs>

          {routed.map(({ key, edge, d }) => (
            <g
              key={key}
              data-dim-wrapper
              className={[
                "flow-edge",
                active !== null && touches(edge) ? "wire-active" : "",
                touches(edge) ? "" : "dimmed",
              ].filter(Boolean).join(" ")}
            >
              <path data-flow-edge={`${edge.from}-${edge.to}`} d={d}
                    markerEnd="url(#flow-tip)" />
            </g>
          ))}

          {boxes.map((box) => (
            <g
              key={box.id}
              data-step={box.id}
              data-dim-wrapper
              className={near(box.id) ? "flow-node" : "flow-node dimmed"}
              role="button"
              tabIndex={0}
              aria-label={pick(box.label, lang)}
              onMouseEnter={() => setActive(box.id)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(box.id)}
              onBlur={() => setActive(null)}
            >
              <rect
                className={`flow-box flow-${box.kind}`}
                x={box.x} y={box.y} width={BOX_WIDTH} height={box.h} rx={8}
              />
              <text className="flow-label" textAnchor="middle">
                {wrapLabel(pick(box.label, lang), LABEL_CHARS).map((line, i, all) => (
                  <tspan
                    key={i}
                    x={box.x + BOX_WIDTH / 2}
                    y={box.y + (box.h - all.length * LINE_HEIGHT) / 2
                      + BOX_PADDING + i * LINE_HEIGHT}
                  >
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          ))}
        </svg>

        {shown.map(({ key, edge, midX, midY }) => (
          <div key={key} className="wire-label" style={{ left: midX, top: midY }}>
            <span>{pick(edge.label as L, lang)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
