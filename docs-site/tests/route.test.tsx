import { describe, expect, it, beforeEach } from "vitest";
import { parseRoute, formatRoute, popOne } from "../src/route";

describe("route", () => {
  beforeEach(() => { window.location.hash = ""; });

  it("round-trips every segment", () => {
    const r = parseRoute("#/vi/c/ingest-tables/fn/parse_table_region");
    expect(r.lang).toBe("vi");
    expect(r.view).toBe("c");
    expect(r.id).toBe("ingest-tables");
    expect(r.sub).toEqual({ kind: "fn", id: "parse_table_region" });
    expect(formatRoute(r)).toBe("#/vi/c/ingest-tables/fn/parse_table_region");
  });

  it("Escape peels exactly one layer, not the whole stack", () => {
    const deep = parseRoute("#/vi/c/ingest-tables/fn/parse_table_region");
    const once = popOne(deep);
    expect(formatRoute(once)).toBe("#/vi/c/ingest-tables");
    const twice = popOne(once);
    expect(formatRoute(twice)).toBe("#/vi/grid");
  });

  it("keeps the language when a layer is peeled", () => {
    const r = popOne(parseRoute("#/en/c/ingest-tables/fn/x"));
    expect(r.lang).toBe("en");
  });

  it("round-trips a sub-route on a view that has no id", () => {
    // The map has no id of its own, so selecting a wire produced
    // #/vi/map/edge/frontend~api, which parsed back as id "edge" and NO
    // selection — the panel never opened.
    const r = parseRoute("#/vi/map/-/edge/frontend~api");
    expect(r.id).toBeNull();
    expect(r.sub).toEqual({ kind: "edge", id: "frontend~api" });
    expect(formatRoute(r)).toBe("#/vi/map/-/edge/frontend~api");
    expect(formatRoute({ lang: "vi", view: "map", id: null, phase: null,
                         sub: { kind: "edge", id: "frontend~api" } }))
      .toBe("#/vi/map/-/edge/frontend~api");
  });

  it("peels a sub-route off a view that has no id", () => {
    const r = popOne(parseRoute("#/vi/map/-/edge/frontend~api"));
    expect(r.sub).toBeNull();
    expect(formatRoute(r)).toBe("#/vi/map");
  });

  it("keeps the phase filter across a peel", () => {
    const r = popOne(parseRoute("#/vi/c/ingest-tables?phase=p2"));
    expect(r.phase).toBe("p2");
    expect(formatRoute(r)).toBe("#/vi/grid?phase=p2");
  });
});
