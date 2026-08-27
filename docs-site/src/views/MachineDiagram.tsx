import { useState } from "react";
import { content } from "../content";
import { pick, type L } from "../i18n";
import type { Lang, Route } from "../route";
import {
  BOX_PADDING, LABEL_CHARS, LINE_HEIGHT,
  columnGap, labelHeight, laneOffsets, wirePath, wrapLabel,
} from "../svg/layout";
import { DiagramText, type TextSection } from "./DiagramText";
import { PhaseFilter } from "./PhaseFilter";

const BOX_WIDTH = 200;
const ROW_GAP = 20;
const INLET_GAP = 72;

type Machine = (typeof content.machines.machines)[number];

function sections(machine: Machine): TextSection[] {
  const label = (id: string) => {
    const part = machine.parts.find((p) => p.id === id);
    if (part) return part.label;
    const exit = machine.exits.find((x) => x.id === id);
    return exit ? exit.label : { vi: id, en: id, fr: id };
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
          fr: `${pick(label(e.from), "fr")} -> ${pick(label(e.to), "fr")}`,
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
  const [active, setActive] = useState<string | null>(null);
  const machine = content.machines.machines.find((m) => m.id === id)
    ?? content.machines.machines[0];

  // Measured from the number of lines crossing it, so two branches leaving
  // the same part cannot land on the same spot. No edge crosses the INLET
  // gap - the inlet names what goes in, it is not wired to a part - so that
  // one gets a plain margin instead.
  const COL_GAP = columnGap(machine.edges.length);

  const partX = 16 + BOX_WIDTH + INLET_GAP;
  let y = 16;
  const parts = machine.parts.map((part) => {
    const h = labelHeight(part.label);
    const box = { ...part, x: partX, y, h };
    y += h + ROW_GAP;
    return box;
  });

  const exitX = partX + BOX_WIDTH + COL_GAP;
  let ey = 16;
  const exits = machine.exits.map((exit) => {
    const h = labelHeight(exit.label);
    const box = { ...exit, x: exitX, y: ey, h };
    ey += h + ROW_GAP;
    return box;
  });

  const inletH = labelHeight(machine.inlet.label);
  const byId = new Map<string, { x: number; y: number; h: number }>(
    [...parts, ...exits].map((b) => [b.id, { x: b.x, y: b.y, h: b.h }]));
  const offsets = laneOffsets(machine.edges.length);

  const routed = machine.edges.map((edge, i) => {
    const from = byId.get(edge.from);
    const to = byId.get(edge.to);
    if (!from || !to) return null;
    const y1 = from.y + from.h / 2;
    const y2 = to.y + to.h / 2;
    const turnX = from.x + BOX_WIDTH + COL_GAP / 2 + offsets[i];
    // Every part shares one column, so a part -> part wire comes back into the
    // target's RIGHT edge; only the exits sit further right. Ending at to.x
    // ran each wire through its own target and struck out the label.
    const endX = to.x > from.x ? to.x : to.x + BOX_WIDTH;
    return {
      key: `${edge.from}-${edge.to}-${i}`, edge,
      d: wirePath(from.x + BOX_WIDTH, y1, turnX, endX, y2),
      midX: turnX, midY: (y1 + y2) / 2,
    };
  }).filter((r): r is NonNullable<typeof r> => r !== null);

  const width = exitX + BOX_WIDTH + 16;
  const height = Math.max(y, ey, inletH + 32) + 16;

  const touches = (edge: { from: string; to: string }) =>
    active === null || edge.from === active || edge.to === active;
  const near = (boxId: string) => active === null || boxId === active
    || routed.some(({ edge }) => (edge.from === active && edge.to === boxId)
      || (edge.to === active && edge.from === boxId));
  const shown = routed.filter((r) => active !== null && touches(r.edge) && r.edge.label);

  const box = (key: string, x: number, yy: number, h: number,
               label: L, className: string) => {
    const lines = wrapLabel(pick(label, lang), LABEL_CHARS);
    return (
      <g key={key} role="img" aria-label={pick(label, lang)}>
        <rect className={className} x={x} y={yy} width={BOX_WIDTH} height={h} rx={8} />
        <text className="flow-label" textAnchor="middle">
          {lines.map((line, i) => (
            <tspan
              key={i} x={x + BOX_WIDTH / 2}
              y={yy + (h - lines.length * LINE_HEIGHT) / 2 + BOX_PADDING
                + i * LINE_HEIGHT}
            >
              {line}
            </tspan>
          ))}
        </text>
      </g>
    );
  };

  return (
    <div className="layer layer-machine">
      <nav className="machine-tabs" role="group"
           aria-label={pick(content.ui.aria.machineSwitch, lang)}>
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
        <div
          className={`board${active ? " board-spotlight" : ""}`}
          style={{ width, height }}
        >
          <svg
            className="machine" width={width} height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="group" aria-label={pick(machine.label, lang)}
          >
            <defs>
              <marker
                id="machine-tip" viewBox="0 0 8 8" refX="6.5" refY="4"
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
                <path data-machine-edge={`${edge.from}-${edge.to}`} d={d}
                      markerEnd="url(#machine-tip)" />
              </g>
            ))}

            {box("inlet", 16, 16, inletH, machine.inlet.label, "flow-box flow-inlet")}

            {parts.map((part) => {
              const lit = phase === null || part.phases.includes(phase);
              return (
                // The dimming class sits on the WRAPPER <g>, never on the rect.
                <g
                  key={part.id}
                  data-part={part.id}
                  data-dim-wrapper
                  className={lit && near(part.id) ? undefined : "dimmed"}
                  role="button"
                  tabIndex={0}
                  aria-label={pick(part.label, lang)}
                  onMouseEnter={() => setActive(part.id)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(part.id)}
                  onBlur={() => setActive(null)}
                >
                  {box(part.id, part.x, part.y, part.h, part.label,
                       "flow-box flow-step")}
                </g>
              );
            })}

            {exits.map((exit) => (
              <g
                key={exit.id}
                data-exit={exit.id}
                data-dim-wrapper
                className={near(exit.id) ? undefined : "dimmed"}
              >
                {box(exit.id, exit.x, exit.y, exit.h, exit.label,
                     "flow-box flow-exit")}
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

      <DiagramText sections={sections(machine)} lang={lang} />
    </div>
  );
}
