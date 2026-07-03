import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LedgerRAG",
  description: "Self-hosted multilingual document Q&A with honest table parsing",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900">
        <header className="border-b bg-white">
          <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
            <a href="/" className="text-lg font-semibold tracking-tight">
              LedgerRAG
            </a>
            <span className="text-xs text-slate-500">
              parse it right, or fail honestly
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
