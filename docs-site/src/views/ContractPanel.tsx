import { useState } from "react";
import { content, type Citation } from "../content";
import { sourceUrl } from "../forge";
import { pick } from "../i18n";
import type { Lang, Route } from "../route";
import { Citation as Source } from "./Citation";

type Edge = (typeof content.edges.edges)[number];
type Operation = { method: string; path: string; auth: Localized;
  request: Localized; response: Localized;
  errors: { code: string; meaning: Localized }[]; cite?: Citation };
type Localized = { vi: string; en: string; fr: string };

/** One wire carries one or more contract families; a family carries its
 *  operations. Sixty-one endpoints are not sixty-one arrows: the board stays
 *  readable and the contract stays complete. */
export function ContractPanel(
  { wire, lang, route, go }: {
    wire: Edge[]; lang: Lang; route?: Route; go?: (next: Route) => void;
  },
) {
  // The first family opens with the panel. A wire that answers a click with
  // nothing but a list of names has not told the reader anything yet.
  const [openFamily, setOpenFamily] = useState<string | null>(wire[0].id);

  const close = () => { if (route && go) go({ ...route, sub: null }); };
  const from = content.nodes.nodes.find((n) => n.id === wire[0].from)!;
  const to = content.nodes.nodes.find((n) => n.id === wire[0].to)!;

  return (
    <aside className="panel panel-contract">
      <header className="panel-head">
        <h2>
          <span>{pick(from.label, lang)}</span>
          <span className="arrow" aria-hidden="true">{"→"}</span>
          <span>{pick(to.label, lang)}</span>
        </h2>
        <button
          type="button" className="close"
          aria-label={pick(content.ui.aria.closePanel, lang)}
          onClick={close}
        >
          {pick(content.ui.actions.close, lang)}
        </button>
      </header>

      <ul className="families">
        {wire.map((family) => {
          const isOpen = openFamily === family.id;
          const operations = (family.operations ?? []) as Operation[];
          return (
            <li key={family.id} className={isOpen ? "family open" : "family"}>
              <button
                type="button"
                className="family-head"
                aria-expanded={isOpen}
                onClick={() => setOpenFamily(isOpen ? null : family.id)}
              >
                <span className="family-name">{pick(family.label, lang)}</span>
                {operations.length ? (
                  <span className="count">{operations.length}</span>
                ) : null}
              </button>

              {isOpen ? (
                <div className="family-body">
                  <p className="family-summary">{pick(family.summary, lang)}</p>
                  {"cite" in family && family.cite ? (
                    <Source cite={family.cite as Citation} lang={lang} />
                  ) : null}

                  {operations.map((op) => (
                    <article className="op" key={`${op.method} ${op.path}`}>
                      <div className="op-head">
                        <code className={`method method-${op.method.toLowerCase()}`}>
                          {op.method}
                        </code>
                        <code className="path">{op.path}</code>
                        {/* A guard requires every operation to cite its
                            handler, so this is never absent in practice; it
                            is written as a condition anyway, because the
                            version that assumed otherwise took the whole
                            page down with it. */}
                        {op.cite ? (
                          <a
                            className="op-source"
                            href={sourceUrl(op.cite.file, op.cite.from, op.cite.to)}
                            target="_blank" rel="noreferrer"
                          >
                            {pick(content.ui.actions.openSource, lang)}
                          </a>
                        ) : null}
                      </div>
                      <dl className="op-body">
                        <dt>{pick(content.ui.labels.auth, lang)}</dt>
                        <dd>{pick(op.auth, lang)}</dd>
                        <dt>{pick(content.ui.labels.request, lang)}</dt>
                        <dd>{pick(op.request, lang)}</dd>
                        <dt>{pick(content.ui.labels.response, lang)}</dt>
                        <dd>{pick(op.response, lang)}</dd>
                        {op.errors.length ? (
                          <>
                            <dt>{pick(content.ui.labels.errors, lang)}</dt>
                            <dd>
                              <ul className="errors">
                                {op.errors.map((error) => (
                                  <li key={error.code}>
                                    <code>{error.code}</code>
                                    <span>{pick(error.meaning, lang)}</span>
                                  </li>
                                ))}
                              </ul>
                            </dd>
                          </>
                        ) : null}
                      </dl>
                    </article>
                  ))}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
