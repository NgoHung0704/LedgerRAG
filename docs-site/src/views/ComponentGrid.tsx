import { content, type Component } from "../content";
import { pick } from "../i18n";
import type { Lang, Route } from "../route";
import { Citation } from "./Citation";
import { PhaseFilter, matchesPhase } from "./PhaseFilter";

const RELATION_KEY = {
  creates: "creates", modifies: "modifies", traverses: "traverses",
} as const;

function PhaseBadges({ component, lang }: { component: Component; lang: Lang }) {
  return (
    <ul className="rel-list">
      {component.phases.map((rel) => {
        const phase = content.phases.phases.find((p) => p.id === rel.id)!;
        return (
          <li key={`${rel.id}-${rel.relation}`} className={`rel rel-${rel.relation}`}>
            <span className="rel-phase">{pick(phase.label, lang)}</span>
            <span className="rel-kind">
              {pick(content.ui.labels[
                RELATION_KEY[rel.relation as keyof typeof RELATION_KEY]], lang)}
            </span>
            <Citation cite={rel.cite} lang={lang} />
          </li>
        );
      })}
    </ul>
  );
}

function ComponentCard(
  { component, lang, onOpen }: {
    component: Component; lang: Lang; onOpen?: () => void;
  },
) {
  return (
    <article className={`card card-${component.group}`}>
      <h3>
        <button type="button" className="card-open" onClick={onOpen}>
          {pick(component.label, lang)}
        </button>
      </h3>
      <p className="card-summary">{pick(component.summary, lang)}</p>
      <PhaseBadges component={component} lang={lang} />
      <details className="card-modules">
        <summary>
          {`${pick(content.ui.labels.modules, lang)} (${component.modules.length})`}
        </summary>
        <ul>
          {component.modules.map((module) => (
            <li key={module}><code>{module}</code></li>
          ))}
        </ul>
      </details>
    </article>
  );
}

export function ComponentGrid(
  { lang, phase, route, go }: {
    lang: Lang; phase: string | null;
    route?: Route; go?: (next: Route) => void;
  },
) {
  const components = content.components.components;
  const anyLit = components.some((c) => matchesPhase(c, phase));

  return (
    <div className="layer layer-grid">
      <PhaseFilter lang={lang} route={route} go={go} />

      <p className="hint">{pick(content.ui.hints.selectComponent, lang)}</p>

      {anyLit ? null : (
        <p className="empty">{pick(content.ui.empty.noPhaseMatch, lang)}</p>
      )}

      <ul className="grid">
        {components.map((component) => {
          const lit = matchesPhase(component, phase);
          return (
            // The dimming class sits on the WRAPPER. Put it on the card and
            // two opacity rules fight each other instead of multiplying.
            <li
              key={component.id}
              data-dim-wrapper
              className={lit ? undefined : "dimmed"}
              aria-current={lit}
            >
              <ComponentCard
                component={component}
                lang={lang}
                onOpen={() => {
                  if (!route || !go) return;
                  go({ ...route, view: "c", id: component.id, sub: null });
                }}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
