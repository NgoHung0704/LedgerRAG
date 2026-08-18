import { afterEach, describe, expect, it } from "vitest";

import { middleware } from "./middleware";

const request = () =>
  ({ nextUrl: new URL("http://host/embed/tok"), headers: new Headers() }) as never;

const csp = () =>
  middleware(request()).headers.get("content-security-policy");

afterEach(() => {
  delete process.env.EMBED_FRAME_ANCESTORS;
});

describe("framing the embed", () => {
  it("forbids it when nobody has been named", () => {
    // the first version of this guard read the file as text and looked for
    // "'none'" — which also appears in the comment above the code, so changing
    // the default to "*" left it green
    expect(csp()).toBe("frame-ancestors 'none'");
  });

  it("forbids it when the variable is set but empty or blank", () => {
    for (const blank of ["", "   "]) {
      process.env.EMBED_FRAME_ANCESTORS = blank;
      expect(csp()).toBe("frame-ancestors 'none'");
    }
  });

  it("allows exactly the origins named", () => {
    process.env.EMBED_FRAME_ANCESTORS = "https://intranet.example.com";
    expect(csp()).toBe("frame-ancestors https://intranet.example.com");
  });

  it("only applies to the embed path", async () => {
    const { config } = await import("./middleware");
    expect(config.matcher).toBe("/embed/:path*");
  });
});
