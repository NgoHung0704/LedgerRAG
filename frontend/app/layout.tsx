import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import "./globals.css";
import AppShell from "@/components/AppShell";
import { LocaleProvider } from "@/components/LocaleProvider";
import { DEFAULT_LOCALE, isLocale, LOCALE_COOKIE } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "LedgerRAG",
  description: "Self-hosted multilingual document Q&A with honest table parsing",
};

// `maximumScale` is deliberately left alone: pinch-zoom is how a lot of people
// read a dense table on a phone, and locking it out is an accessibility failure.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f3ec" },
    { media: "(prefers-color-scheme: dark)", color: "#0f141a" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // reading a cookie makes this route dynamic, which it already is: every page
  // in this app is behind auth and shows live data. It buys the thing a
  // localStorage read cannot — the FIRST paint is already in the right
  // language, because a language is content and the server renders content.
  const saved = cookies().get(LOCALE_COOKIE)?.value;
  const locale = isLocale(saved) ? saved : DEFAULT_LOCALE;

  return (
    <html lang={locale} suppressHydrationWarning>
      <head>
        {/* apply the saved theme before first paint, so there's no flash */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('theme');if(t==='dark'||(!t&&matchMedia('(prefers-color-scheme:dark)').matches))document.documentElement.classList.add('dark')}catch(e){}",
          }}
        />
      </head>
      <body>
        <LocaleProvider locale={locale}>
          <AppShell>{children}</AppShell>
        </LocaleProvider>
      </body>
    </html>
  );
}
