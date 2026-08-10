import { content, type MapEdge } from "../content";
import { githubUrl } from "../github";
import { pick } from "../i18n";
import type { Lang, Route } from "../route";
import { Citation } from "./Citation";

/** One edge is one contract family. 61 endpoints are not 61 arrows; the
 *  diagram stays readable and the contract stays complete. */
export function ContractPanel(
  { edge, lang, route, go }: {
    edge: MapEdge; lang: Lang; route?: Route; go?: (next: Route) => void;
  },
) {
  const close = () => { if (route && go) go({ ...route, sub: null }); };

  return (
    <aside className="panel panel-contract">
      <header className="panel-head">
        <h2>{pick(edge.label, lang)}</h2>
        <button
          type="button"
          className="close"
          aria-label={pick(content.ui.aria.closePanel, lang)}
          onClick={close}
        >
          {pick(content.ui.actions.close, lang)}
        </button>
      </header>

      <p className="panel-summary">{pick(edge.summary, lang)}</p>

      {"cite" in edge && edge.cite
        ? <Citation cite={edge.cite} lang={lang} />
        : null}

      <ul className="ops">
        {(edge.operations ?? []).map((op) => (
          <li className="op" key={`${op.method} ${op.path}`}>
            <div className="op-head">
              <code className={`method method-${op.method.toLowerCase()}`}>
                {op.method}
              </code>
              <code className="path">{op.path}</code>
              <a
                className="op-source"
                href={githubUrl(op.cite.file, op.cite.from, op.cite.to)}
                target="_blank"
                rel="noreferrer"
              >
                {pick(content.ui.actions.openOnGitHub, lang)}
              </a>
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
          </li>
        ))}
      </ul>
    </aside>
  );
}
