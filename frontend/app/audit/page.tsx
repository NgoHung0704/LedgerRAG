"use client";

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
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAudit()
      .then((r) => setEvents(r.events))
      .catch(() => setError("Admin access required."));
  }, []);

  return (
    <div>
      <h1 className="mb-1 flex items-center gap-2 text-xl font-semibold tracking-tight">
        <ScrollText size={20} /> Audit log
      </h1>
      <p className="mb-5 text-sm text-slate-500">
        Who uploaded, queried, or changed model configuration — GDPR
        accountability, most recent first.
      </p>

      {error && <div className="text-sm text-red-600">{error}</div>}
      {!events && !error && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Spinner size={15} /> Loading…
        </div>
      )}

      {events && events.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-400 shadow-card">
          No activity recorded yet.
        </div>
      )}

      {events && events.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-2.5 font-medium">When</th>
                <th className="px-4 py-2.5 font-medium">Who</th>
                <th className="px-4 py-2.5 font-medium">Action</th>
                <th className="px-4 py-2.5 font-medium">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {events.map((e, i) => {
                const Icon = ICON[e.action] ?? ScrollText;
                return (
                  <tr key={i} className="hover:bg-slate-50">
                    <td className="whitespace-nowrap px-4 py-2.5 text-slate-500">
                      {new Date(e.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 font-medium text-slate-700">
                      {e.actor}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center gap-1.5 text-slate-600">
                        <Icon size={13} /> {e.action}
                      </span>
                    </td>
                    <td className="max-w-md truncate px-4 py-2.5 text-slate-400">
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
