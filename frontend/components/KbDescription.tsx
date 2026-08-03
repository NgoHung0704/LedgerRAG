"use client";

import { type KB } from "@/lib/api";

// Read-only display of the KB's description under its title. Editing (and the
// one-click "Suggest from documents" draft) lives in Settings, so there's a
// single, obvious place to change it — see KbSettings.
export default function KbDescription({ kb }: { kb: KB }) {
  return (
    <div className="mt-1 max-w-2xl">
      <p className="text-sm text-ink-muted">
        {kb.description || (
          <span className="italic text-ink-subtle">
            No description yet — add one in Settings so it can be auto-routed.
          </span>
        )}
      </p>
    </div>
  );
}
