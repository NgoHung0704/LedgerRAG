import type { ComponentDetail } from "../content";
import { pick } from "../i18n";
import type { Lang } from "../route";
import {
  BOX_PADDING, LABEL_CHARS, LINE_HEIGHT,
  boxHeight, columnGap, laneOffsets, wrapLabel,
} from "../svg/layout";

const BOX_WIDTH = 190;
const ROW_GAP = 22;

type Kind = "step" | "gate" | "exit";
type Box = {
  id: string; kind: Kind; label: { vi: string; en: string };
  x: number; y: number; w: number; h: number;
};

/** Steps in the left column, gates in the middle, exits on the right — the
 *  shape a reader already expects from a pipeline drawing. */
export function FlowDiagram(
  { flow, lang }: { flow: NonNullable<ComponentDetail["flow"]>; lang: Lang },
) {
  const columns: { kind: Kind; items: { id: string; label: { vi: string; en: string } }[] }[] = [
    { kind: "step", items: flow.nodes },
    { kind: "gate", items: flow.gates ?? [] },
    { kind: "exit", items: flow.exits ?? [] },
  ];

  // The gap is measured from the number of lines that must cross it. Squeeze
  // the lanes and two branch labels leaving the same gate land on top of
  // each other — which is what the rendered page showed before this.
  const COL_GAP = columnGap(flow.edges.length);

  const boxes: Box[] = [];
  let x = 16;
  columns.forEach(({ kind, items }) => {
    if (!items.length) return;
    let y = 16;
    items.forEach((item) => {
      const h = Math.max(
        boxHeight(wrapLabel(item.label.vi, LABEL_CHARS)),
        boxHeight(wrapLabel(item.label.en, LABEL_CHARS)));
      boxes.push({ id: item.id, kind, label: item.label, x, y, w: BOX_WIDTH, h });
      y += h + ROW_GAP;
    });
    x += BOX_WIDTH + COL_GAP;
  });

  const byId = new Map(boxes.map((b) => [b.id, b]));
  const offsets = laneOffsets(flow.edges.length);

  const width = x + 16;
  const height = Math.max(...boxes.map((b) => b.y + b.h), 40) + 24;

  return (
    <div className="scroll-x">
      <svg
        className="flow"
        width={width} height={height} viewBox={`0 0 ${width} ${height}`}
        role="group" aria-label={pick(flow.nodes[0].label, lang)}
      >
        {flow.edges.map((edge, i) => {
          const from = byId.get(edge.from);
          const to = byId.get(edge.to);
          if (!from || !to) return null;
          const y1 = from.y + from.h / 2;
          const y2 = to.y + to.h / 2;
          const turnX = from.x + from.w + COL_GAP / 2 + offsets[i];
          const d = `M ${from.x + from.w} ${y1} H ${turnX} V ${y2} H ${to.x}`;
          return (
            <g key={`${edge.from}-${edge.to}-${i}`} className="flow-edge">
              <path data-flow-edge={`${edge.from}-${edge.to}`} d={d} />
              {edge.label ? (
                // Turned along its own lane, for the same reason as the
                // system map: flat labels in a shared gap overlap into a smear.
                <text
                  data-edge-label={`${edge.from}-${edge.to}-${i}`}
                  x={turnX} y={(y1 + y2) / 2} textAnchor="middle"
                  transform={`rotate(-90 ${turnX} ${(y1 + y2) / 2})`}
                >
                  {pick(edge.label, lang)}
                </text>
              ) : null}
            </g>
          );
        })}
        {boxes.map((box) => {
          const lines = wrapLabel(pick(box.label, lang), LABEL_CHARS);
          const top = box.y + BOX_PADDING + LINE_HEIGHT * 0.8;
          return (
            <g key={box.id} role="img" aria-label={pick(box.label, lang)}>
              <rect
                className={`flow-box flow-${box.kind}`}
                x={box.x} y={box.y} width={box.w} height={box.h} rx={8}
              />
              <text className="flow-label" textAnchor="middle">
                {lines.map((line, i) => (
                  <tspan key={i} x={box.x + box.w / 2} y={top + i * LINE_HEIGHT}>
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
