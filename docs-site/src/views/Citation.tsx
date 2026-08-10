import { content, type Citation as Cite } from "../content";
import { githubUrl } from "../github";
import { pick } from "../i18n";
import type { Lang } from "../route";

/** Every claim on this page points at lines in the repo, and the link goes to
 *  exactly those lines. The guards in tests/unit/test_docs_content.py fail if
 *  the two ever disagree, so what is shown here is checkable, not decorative. */
export function Citation({ cite, lang }: { cite: Cite; lang: Lang }) {
  return (
    <a
      className="citation"
      href={githubUrl(cite.file, cite.from, cite.to)}
      target="_blank"
      rel="noreferrer"
      title={pick(content.ui.actions.openOnGitHub, lang)}
    >
      <code>
        {cite.from === cite.to
          ? `${cite.file}:${cite.from}`
          : `${cite.file}:${cite.from}-${cite.to}`}
      </code>
    </a>
  );
}
