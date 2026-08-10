import { content, type Component } from "../content";
import { pick } from "../i18n";
import type { Lang, Route } from "../route";

/** Highlight on ANY relation. If only creates/modifies lit up, a phase's
 *  request would appear to stop dead at the components it calls but never
 *  changed — the reader would see a gap where the code has none. */
export const matchesPhase = (component: Component, phase: string | null) =>
  phase === null || component.phases.some((p) => p.id === phase);

export function PhaseFilter(
  { lang, route, go }: {
    lang: Lang; route?: Route; go?: (next: Route) => void;
  },
) {
  const current = route?.phase ?? null;
  const set = (phase: string | null) => {
    if (!route || !go) return;
    go({ ...route, phase });
  };

  return (
    <div className="phase-filter" role="group"
         aria-label={pick(content.ui.aria.phaseFilter, lang)}>
      <button
        type="button"
        className="phase-chip"
        aria-pressed={current === null}
        onClick={() => set(null)}
      >
        {pick(content.ui.labels.allPhases, lang)}
      </button>
      {content.phases.phases.map((phase) => (
        <button
          key={phase.id}
          type="button"
          className="phase-chip"
          aria-pressed={current === phase.id}
          onClick={() => set(current === phase.id ? null : phase.id)}
        >
          {pick(phase.label, lang)}
        </button>
      ))}
    </div>
  );
}
