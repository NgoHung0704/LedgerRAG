import { content } from "../content";
import { githubUrl } from "../github";
import { pick } from "../i18n";
import type { Lang, Route } from "../route";
import { Citation } from "./Citation";
import { CodeExcerpt } from "./CodeExcerpt";
import { DiagramText, type TextSection } from "./DiagramText";
import { FlowDiagram } from "./FlowDiagram";

export function ComponentDetail(
  { id, lang, route, go }: {
    id: string; lang: Lang; route?: Route; go?: (next: Route) => void;
  },
) {
  const component = content.components.components.find((c) => c.id === id);
  const detail = content.componentDetails[id];
  if (!component || !detail) return null;

  const flowSections = (): TextSection[] => {
    if (!detail.flow) return [];
    const label = (key: string) => {
      const all = [...detail.flow!.nodes, ...detail.flow!.gates,
                   ...detail.flow!.exits];
      const hit = all.find((n) => n.id === key);
      return hit ? hit.label : { vi: key, en: key, fr: key };
    };
    return [
      { heading: content.ui.headings.steps,
        entries: detail.flow.nodes.map((n) => ({ label: n.label })) },
      { heading: content.ui.headings.gates,
        entries: detail.flow.gates.map((g) => ({ label: g.label })) },
      { heading: content.ui.headings.edges,
        entries: detail.flow.edges.map((e) => ({
          label: {
            vi: `${pick(label(e.from), "vi")} → ${pick(label(e.to), "vi")}`,
            en: `${pick(label(e.from), "en")} -> ${pick(label(e.to), "en")}`,
            fr: `${pick(label(e.from), "fr")} -> ${pick(label(e.to), "fr")}`,
          },
          detail: e.label,
        })) },
      { heading: content.ui.headings.exits,
        entries: detail.flow.exits.map((x) => ({ label: x.label })) },
    ].filter((section) => section.entries.length > 0);
  };

  return (
    <article className="layer layer-detail">
      <header className="detail-head">
        <h2>{pick(component.label, lang)}</h2>
        <button
          type="button"
          className="close"
          aria-label={pick(content.ui.aria.closePanel, lang)}
          onClick={() => {
            if (route && go) go({ ...route, view: "grid", id: null, sub: null });
          }}
        >
          {pick(content.ui.actions.close, lang)}
        </button>
      </header>

      <p className="detail-summary">{pick(component.summary, lang)}</p>

      {detail.flow ? (
        <section className="detail-flow">
          <h3>{pick(content.ui.headings.flow, lang)}</h3>
          <FlowDiagram flow={detail.flow} lang={lang} />
          <DiagramText sections={flowSections()} lang={lang} />
        </section>
      ) : null}

      <section className="detail-functions">
        <h3>{pick(content.ui.headings.functions, lang)}</h3>
        <ul>
          {detail.functions.map((fn) => (
            <li key={`${fn.file}:${fn.name}`}>
              <code className="decl">{fn.decl}</code>
              <a
                className="fn-source"
                href={githubUrl(fn.file, fn.line, fn.line)}
                target="_blank"
                rel="noreferrer"
              >
                {`${fn.file}:${fn.line}`}
              </a>
              <p>{pick(fn.note, lang)}</p>
            </li>
          ))}
        </ul>
      </section>

      {detail.excerpts.length ? (
        <section className="detail-excerpts">
          <h3>{pick(content.ui.headings.code, lang)}</h3>
          {detail.excerpts.map((item, i) => (
            <CodeExcerpt key={i} caption={item.caption} cite={item.cite} lang={lang} />
          ))}
        </section>
      ) : null}

      {detail.why.length ? (
        <section className="detail-why">
          <h3>{pick(content.ui.labels.why, lang)}</h3>
          <ul className="cards">
            {detail.why.map((card, i) => (
              <li key={i} className="why-card">
                <p>{pick(card.text, lang)}</p>
                <Citation cite={card.cite} lang={lang} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Debts are never collapsed. A handover page that hides what is still
          owed is exactly the failure this page exists to prevent. */}
      {detail.debts.length ? (
        <section className="detail-debts">
          <h3>{pick(content.ui.labels.debt, lang)}</h3>
          <ul className="cards">
            {detail.debts.map((card, i) => (
              <li key={i} className="debt-card">
                <p>{pick(card.text, lang)}</p>
                <Citation cite={card.cite} lang={lang} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
