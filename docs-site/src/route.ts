export type Lang = "vi" | "en" | "fr";
export type View = "map" | "grid" | "c" | "machine";
export type Sub = { kind: "edge" | "fn" | "excerpt"; id: string } | null;

export interface Route {
  lang: Lang; view: View; id: string | null; sub: Sub; phase: string | null;
}

const NO_ID = "-";

const DEFAULT: Route = {
  lang: "vi", view: "map", id: null, sub: null, phase: null,
};

export function parseRoute(hash: string): Route {
  const [pathPart, queryPart] = hash.replace(/^#\/?/, "").split("?");
  const parts = pathPart.split("/").filter(Boolean);
  const phase = new URLSearchParams(queryPart ?? "").get("phase");
  if (parts.length === 0) return { ...DEFAULT, phase };
  const [lang, view, id, subKind, subId] = parts;
  return {
    lang: (["vi", "en", "fr"].includes(lang) ? lang : "vi") as Lang,
    view: (["map", "grid", "c", "machine"].includes(view) ? view : "map") as View,
    id: id && id !== NO_ID ? id : null,
    sub: subKind && subId
      ? { kind: subKind as "edge" | "fn" | "excerpt", id: subId }
      : null,
    phase,
  };
}

export function formatRoute(r: Route): string {
  const parts: string[] = [r.lang, r.view];
  // A view with no id still has to hold a slot when a sub-route follows it,
  // or the sub's two segments slide into the id position and parse back as
  // no sub at all. That is how selecting a wire on the map set a route the
  // map could not read.
  if (r.id) parts.push(r.id);
  else if (r.sub) parts.push(NO_ID);
  if (r.sub) parts.push(r.sub.kind, r.sub.id);
  const query = r.phase ? `?phase=${encodeURIComponent(r.phase)}` : "";
  return `#/${parts.join("/")}${query}`;
}

/** One layer, once. Escape and Back must agree, and neither may skip a rung. */
export function popOne(r: Route): Route {
  if (r.sub) return { ...r, sub: null };
  if (r.view === "c") return { ...r, view: "grid", id: null };
  if (r.view === "machine") return { ...r, view: "grid", id: null };
  if (r.view === "grid") return { ...r, view: "map", id: null };
  return r;
}

export function navigate(next: Route): void {
  const depth = ((window.history.state as { depth?: number } | null)?.depth ?? 0) + 1;
  window.history.pushState({ depth }, "", formatRoute(next));
  // pushState does not fire hashchange; tell the app ourselves.
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}
