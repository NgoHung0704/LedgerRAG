import { useCallback, useEffect, useState } from "react";
import {
  formatRoute, navigate, parseRoute, popOne, type Lang, type Route, type View,
} from "./route";
import { content } from "./content";
import { pick } from "./i18n";
import { SystemMap } from "./views/SystemMap";
import { ComponentGrid } from "./views/ComponentGrid";
import { ComponentDetail } from "./views/ComponentDetail";
import { MachineDiagram } from "./views/MachineDiagram";

function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    window.addEventListener("popstate", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
      window.removeEventListener("popstate", onChange);
    };
  }, []);
  return route;
}

const NAV: { view: View; key: "map" | "grid" | "machines" }[] = [
  { view: "map", key: "map" },
  { view: "grid", key: "grid" },
  { view: "machine", key: "machines" },
];

export function App() {
  const route = useRoute();
  const lang: Lang = route.lang;

  // One listener, owned by the thing that owns the route.
  //
  // stopPropagation does NOT stop other listeners bound to the same target, so
  // a panel that listens on `document` itself would let one Escape close the
  // whole stack and push several history entries. And a mount-order stack is
  // worse: a panel still playing its exit would sit in it and swallow the next
  // key. Neither exists here — panels render from the route and unmount at once.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      const current = parseRoute(window.location.hash);
      const next = popOne(current);
      if (formatRoute(next) === formatRoute(current)) return;
      const depth = (window.history.state as { depth?: number } | null)?.depth ?? 0;
      if (depth > 0) window.history.back();
      else window.history.replaceState({ depth: 0 }, "", formatRoute(next));
      // replaceState does not fire hashchange; tell the app ourselves.
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const go = useCallback((next: Route) => navigate(next), []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <h1 className="site-title">{pick(content.ui.siteTitle, lang)}</h1>
        </div>

        <nav className="nav">
          {NAV.map(({ view, key }) => (
            <button
              key={view}
              type="button"
              className="nav-item"
              aria-current={route.view === view
                || (view === "grid" && route.view === "c") ? "page" : undefined}
              onClick={() => go({ ...route, view, id: null, sub: null })}
            >
              {pick(content.ui.nav[key], lang)}
            </button>
          ))}
        </nav>

        {/* Three buttons rather than one that cycles: with three languages a
            cycling switch makes a reader press it twice to go back, and its
            label can only name one destination. */}
        <div
          className="langs" role="group"
          aria-label={pick(content.ui.aria.languageSwitch, lang)}
        >
          {content.ui.languages.map((entry) => (
            <button
              key={entry.code}
              type="button"
              className="lang"
              aria-pressed={entry.code === lang}
              onClick={() => go({ ...route, lang: entry.code as Lang })}
            >
              {pick(entry.label, lang)}
            </button>
          ))}
        </div>
      </header>

      <p className="tagline">{pick(content.ui.tagline, lang)}</p>

      <main className="main">
        {route.view === "map" && (
          <SystemMap lang={lang} phase={route.phase} route={route} go={go} />
        )}
        {route.view === "grid" && (
          <ComponentGrid lang={lang} phase={route.phase} route={route} go={go} />
        )}
        {route.view === "c" && route.id && (
          <ComponentDetail id={route.id} lang={lang} route={route} go={go} />
        )}
        {route.view === "machine" && (
          <MachineDiagram
            id={route.id ?? content.machines.machines[0].id}
            lang={lang} phase={route.phase} route={route} go={go}
          />
        )}
      </main>
    </div>
  );
}
