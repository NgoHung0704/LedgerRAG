import { content } from "../content";
import { pick, type L } from "../i18n";
import type { Lang } from "../route";

export interface TextEntry { label: L; detail?: L }
export interface TextSection { heading: L; entries: TextEntry[] }

/** The text version of a diagram, generated from the SAME JSON the picture
 *  reads — so it cannot drift from it.
 *
 *  It carries the edge labels, the gate labels and the exits, because those
 *  are where the logic lives. A list of boxes with no edge labels is not an
 *  alternative to a diagram; it is the diagram with its meaning removed. */
export function DiagramText(
  { sections, lang }: { sections: TextSection[]; lang: Lang },
) {
  return (
    <details className="diagram-text" data-testid="diagram-text">
      <summary>{pick(content.ui.actions.showTextVersion, lang)}</summary>
      {sections.map((section) => (
        <section key={pick(section.heading, "en")}>
          <h3>{pick(section.heading, lang)}</h3>
          <ul>
            {section.entries.map((entry, i) => (
              <li key={i}>
                <span className="dt-label">{pick(entry.label, lang)}</span>
                {entry.detail
                  ? <span className="dt-detail">{pick(entry.detail, lang)}</span>
                  : null}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </details>
  );
}
