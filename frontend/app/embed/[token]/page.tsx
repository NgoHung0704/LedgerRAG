import { LocaleProvider } from "@/components/LocaleProvider";
import { DEFAULT_LOCALE, isLocale } from "@/lib/i18n";

import EmbedChat from "./EmbedChat";

/** The embedded assistant, in the host application's language.
 *
 *  A server component purely so it can read `?lang=`. Measured rather than
 *  assumed: a root LAYOUT receives no searchParams — probing this version
 *  printed `undefined` — but a PAGE does, so reading it here means the first
 *  paint is already in the right language instead of flashing English and
 *  swapping. The embed carries no language picker and its visitor has no cookie
 *  of ours, so without this every embed would render in English; the host knows
 *  its own user's language and passes it.
 *
 *  The provider nests inside the layout's, and the inner one wins for its
 *  subtree. */
export default function EmbedPage({
  params,
  searchParams,
}: {
  params: { token: string };
  searchParams?: { lang?: string };
}) {
  const asked = searchParams?.lang;
  const locale = isLocale(asked) ? asked : DEFAULT_LOCALE;
  return (
    <LocaleProvider locale={locale}>
      <EmbedChat token={params.token} />
    </LocaleProvider>
  );
}
