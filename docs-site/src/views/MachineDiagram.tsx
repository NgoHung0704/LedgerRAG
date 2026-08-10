import { content } from "../content";
import { pick } from "../i18n";
import type { Lang, Route } from "../route";
import {
  BOX_PADDING, LABEL_CHARS, LINE_HEIGHT, boxHeight, laneOffsets, wrapLabel,
} from "../svg/layout";
import { DiagramText, type TextSection } from "./DiagramText";
import { PhaseFilter } from "./PhaseFilter";

const BOX_WIDTH = 200;
const COL_GAP = 120;
const ROW_GAP = 20;

type Machine = (typeof content.machines.machines)[number];

function sections(machine: Machine): TextSection[] {
  const label = (id: string) => {
    const part = machine.parts.find((p) => p.id === id);
    if (part) return part.label;
    const exit = machine.exits.find((x) => x.id === id);
    return exit ? exit.label : { vi: id, en: id };
  };
  return [
    { heading: content.ui.headings.inlet, entries: [{ label: machine.inlet.label }] },
    { heading: content.ui.headings.steps,
      entries: machine.parts.map((p) => ({ label: p.label })) },
    { heading: content.ui.headings.edges,
      entries: machine.edges.map((e) => ({
        label: {
          vi: `${pick(label(e.from), "vi")} → ${pick(label(e.to), "vi")}`,
          en: `${pick(label(e.from), "en")} -> ${pick(label(e.to), "en")}`,
        },
        detail: e.label,
      })) },
    { heading: content.ui.headings.exits,
      entries: machine.exits.map((x) => ({ label: x.label })) },
  ];
}

export function MachineDiagram(
  { id, lang, phase, route, go }: {
    id: string; lang: Lang; phase: string | null;
    route?: Route; go?: (next: Route) => void;
  },
) {
  const machine = content.machines.machines.find((m) => m.id === id)
    ?? content.machines.machines[0];

  const size = (label: { vi: string; en: string }) => Math.max(
    boxHeight(wrapLabel(label.vi, LABEL_CHARS)),
    boxHeight(wrapLabel(label.en, LABEL_CHARS)));

  const partX = 16 + BOX_WIDTH + COL_GAP;
  let y = 16;
  const parts = machine.parts.map((part) => {
    const h = size(part.label);
    const box = { ...part, x: partX, y, h };
    y += h + ROW_GAP;
    return box;
  });

  const exitX = partX + BOX_WIDTH + COL_GAP;
  let ey = 16;
  const exits = machine.exits.map((exit) => {
    const h = size(exit.label);
    const box = { ...exit, x: exitX, y: ey, h };
    ey += h + ROW_GAP;
    return box;
  });

  const inletH = size(machine.inlet.label);
  const byId = new Map<string, { x: number; y: number; h: number }>(
    [...parts, ...exits].map((b) => [b.id, { x: b.x, y: b.y, h: b.h }]));
  const offsets = laneOffsets(machine.edges.length);

  const width = exitX + BOX_WIDTH + 16;
  const height = Math.max(y, ey, inletH + 32) + 16;

  const box = (
    key: string, x: number, yy: number, h: number,
    label: { vi: string; en: string }, className: string,
  ) => {
    const lines = wrapLabel(pick(label, lang), LABEL_CHARS);
    const top = yy + BOX_PADDING + LINE_HEIGHT * 0.8;
    return (
      <g key={key} role="img" aria-label={pick(label, lang)}>
        <rect className={className} x={x} y={yy} width={BOX_WIDTH} height={h} rx={8} />
        <text className="flow-label" textAnchor="middle">
          {lines.map((line, i) => (
            <tspan key={i} x={x + BOX_WIDTH / 2} y={top + i * LINE_HEIGHT}>
              {line}
            </tspan>
          ))}
        </text>
      </g>
    );
  };

  return (
    <div className="layer layer-machine">
      <nav className="machine-tabs">
        {content.machines.machines.map((m) => (
          <button
            key={m.id}
            type="button"
            className="machine-tab"
            aria-pressed={m.id === machine.id}
            onClick={() => { if (route && go) go({ ...route, view: "machine", id: m.id }); }}
          >
            {pick(m.label, lang)}
          </button>
        ))}
      </nav>

      <PhaseFilter lang={lang} route={route} go={go} />

      <div className="scroll-x">
        <svg
          className="machine"
          width={width} height={height} viewBox={`0 0 ${width} ${height}`}
          role="group" aria-label={pick(machine.label, lang)}
        >
          {machine.edges.map((edge, i) => {
            const from = byId.get(edge.from);
            const to = byId.get(edge.to);
            if (!from || !to) return null;
            const y1 = from.y + from.h / 2;
            const y2 = to.y + to.h / 2;
            const turnX = from.x + BOX_WIDTH + COL_GAP / 2 + offsets[i] / 2;
            const d = `M ${from.x + BOX_WIDTH} ${y1} H ${turnX} V ${y2} H ${to.x}`;
            return (
              <g key={`${edge.from}-${edge.to}-${i}`} className="flow-edge">
                <path data-machine-edge={`${edge.from}-${edge.to}`} d={d} />
                {edge.label ? (
                  <text x={turnX} y={(y1 + y2) / 2 - 4} textAnchor="middle">
                    {pick(edge.label, lang)}
                  </text>
                ) : null}
              </g>
            );
          })}

          {box("inlet", 16, 16, inletH, machine.inlet.label, "flow-box flow-inlet")}

          {parts.map((part) => {
            const lit = phase === null || part.phases.includes(phase);
            return (
              // The dimming class sits on the WRAPPER <g>, never on the rect.
              <g
                key={part.id}
                data-part={part.id}
                data-dim-wrapper
                className={lit ? undefined : "dimmed"}
              >
                {box(part.id, part.x, part.y, part.h, part.label, "flow-box flow-step")}
              </g>
            );
          })}

          {exits.map((exit) =>
            box(exit.id, exit.x, exit.y, exit.h, exit.label, "flow-box flow-exit"))}
        </svg>
      </div>

      <DiagramText sections={sections(machine)} lang={lang} />
    </div>
  );
}
