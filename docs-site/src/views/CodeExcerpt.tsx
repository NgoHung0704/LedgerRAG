import type { Citation as Cite } from "../content";
import { pick, type L } from "../i18n";
import type { Lang } from "../route";
import { Citation } from "./Citation";

/** The real lines, not a paraphrase of them. `cite.code` is byte-for-byte what
 *  the file holds — a guard fails the build the moment it stops being. */
export function CodeExcerpt(
  { caption, cite, lang }: { caption: L; cite: Cite; lang: Lang },
) {
  return (
    <figure className="excerpt">
      <figcaption>{pick(caption, lang)}</figcaption>
      <pre><code>{cite.code ?? cite.anchor}</code></pre>
      <Citation cite={cite} lang={lang} />
    </figure>
  );
}
