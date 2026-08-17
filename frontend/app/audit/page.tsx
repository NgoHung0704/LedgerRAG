"use client";

import { useT } from "@/components/LocaleProvider";
import { useEffect, useState } from "react";
import {
  ScrollText,
  Upload,
  MessageSquare,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";
import { getAudit, type AuditEvent } from "@/lib/api";
import { Spinner } from "@/components/ui";

const ICON: Record<string, LucideIcon> = {
  upload: Upload,
  query: MessageSquare,
  model_config: SlidersHorizontal,
};

export default function AuditPage() {
  const t = useT();
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAudit()
      .then((r) => setEvents(r.events))
      .catch(() => setError(t("audit.admin_only")));
  }, []);

  return (
    <div>
      <h1 className="mb-1 flex items-center gap-2 text-xl font-semibold tracking-tight">
        <ScrollText size={20} /> {t("audit.title")}
      </h1>
      <p className="mb-5 text-sm text-ink-muted">
        {t("audit.lede")}
      </p>

      {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
      {!events && !error && (
        <div className="flex items-center gap-2 text-sm text-ink-subtle">
          <Spinner size={15} /> {t("common.loading")}
        </div>
      )}

      {events && events.length === 0 && (
        <div className="rounded-xl border border-line bg-surface p-8 text-center text-sm text-ink-subtle shadow-card">
          {t("audit.empty")}
        </div>
      )}

      {events && events.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-card">
          <table className="w-full text-sm">
            <thead className="bg-surface-sunken text-left text-[11px] uppercase tracking-wide text-ink-subtle dark:bg-slate-800/60">
              <tr>
                <th className="px-4 py-2.5 font-medium">{t("audit.col_when")}</th>
                <th className="px-4 py-2.5 font-medium">{t("audit.col_who")}</th>
                <th className="px-4 py-2.5 font-medium">{t("audit.col_action")}</th>
                <th className="px-4 py-2.5 font-medium">{t("audit.col_detail")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {events.map((e, i) => {
                const Icon = ICON[e.action] ?? ScrollText;
                return (
                  <tr key={i} className="hover:bg-surface-sunken dark:hover:bg-slate-800/50">
                    <td className="whitespace-nowrap px-4 py-2.5 text-ink-muted">
                      {new Date(e.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 font-medium text-ink">
                      {e.actor}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center gap-1.5 text-ink-muted">
                        <Icon size={13} /> {e.action}
                      </span>
                    </td>
                    <td className="max-w-md truncate px-4 py-2.5 text-ink-subtle">
                      {e.detail ? JSON.stringify(e.detail) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
