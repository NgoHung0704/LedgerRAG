import { content } from "../content";
import { pick } from "../i18n";
import type { Lang } from "../route";
import { Citation } from "./Citation";

const componentLabel = (id: string, lang: Lang): string => {
  const component = content.components.components.find((c) => c.id === id);
  return component ? pick(component.label, lang) : id;
};

/** Who owns a store, and who is allowed to write it.
 *
 *  This is where principle 1 stops being a sentence: ingestion/ and query/
 *  never import each other, so the only place their names appear together is
 *  a row of this table. */
export function OwnershipTable(
  { lang, phase }: { lang: Lang; phase: string | null },
) {
  const lit = (id: string) => {
    if (!phase) return true;
    const component = content.components.components.find((c) => c.id === id);
    return !!component?.phases.some((p) => p.id === phase);
  };

  return (
    <section className="ownership">
      <h2>{pick(content.ui.headings.ownership, lang)}</h2>
      <div className="scroll-x">
        <table>
          <thead>
            <tr>
              <th>{pick(content.ui.labels.store, lang)}</th>
              <th>{pick(content.ui.labels.owns, lang)}</th>
              <th>{pick(content.ui.labels.writes, lang)}</th>
              <th>{pick(content.ui.labels.reads, lang)}</th>
              <th>{pick(content.ui.labels.note, lang)}</th>
              <th>{pick(content.ui.labels.source, lang)}</th>
            </tr>
          </thead>
          <tbody>
            {content.ownership.rows.map((row) => (
              <tr
                key={`${row.store}:${row.name}`}
                data-dim-wrapper
                className={lit(row.owner) ? undefined : "dimmed"}
              >
                <td><code>{`${row.store}:${row.name}`}</code></td>
                <td>{componentLabel(row.owner, lang)}</td>
                <td>{row.writers.map((w) => componentLabel(w, lang)).join(" · ")}</td>
                <td>{row.readers.map((r) => componentLabel(r, lang)).join(" · ")}</td>
                <td>{pick(row.note, lang)}</td>
                <td><Citation cite={row.cite} lang={lang} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
