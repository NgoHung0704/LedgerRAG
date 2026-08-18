import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** Who may put the embedded assistant in an iframe.
 *
 *  Read per request rather than at build time, so a deployment changes it by
 *  restarting the container instead of rebuilding the image.
 *
 *  The default is 'none'. An embed that frames anywhere until somebody thinks
 *  to close it is a decision nobody made; this way opening it is one line in
 *  the environment, with a person behind it. */
export function middleware(request: NextRequest) {
  const response = NextResponse.next({ request });
  const origins = (process.env.EMBED_FRAME_ANCESTORS ?? "").trim();
  response.headers.set(
    "Content-Security-Policy",
    `frame-ancestors ${origins || "'none'"}`,
  );
  return response;
}

export const config = { matcher: "/embed/:path*" };
