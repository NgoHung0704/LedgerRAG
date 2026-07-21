"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  FileText,
  Globe,
  MessageSquareText,
  AlertTriangle,
} from "lucide-react";
import { getKb, getKbs, getNeedsReview, type KB } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";
import DocumentsPanel from "@/components/DocumentsPanel";
import KbDescription from "@/components/KbDescription";
import ReviewPanel from "@/components/ReviewPanel";

type Tab = "documents" | "chat" | "review";

export default function KBPage({ params }: { params: { id: string } }) {
  const kbId = params.id;
  const [kb, setKb] = useState<KB | null>(null);
  const [allKbs, setAllKbs] = useState<KB[]>([]);
  const [tab, setTab] = useState<Tab>("documents");
  const [reviewCount, setReviewCount] = useState(0);

  useEffect(() => {
    getKb(kbId).then(setKb).catch(() => {});
    getKbs().then(setAllKbs).catch(() => {});
    getNeedsReview(kbId)
      .then((r) => setReviewCount(r.count))
      .catch(() => {});
  }, [kbId]);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4">
        <Link
          href="/"
          className="mb-2 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600"
        >
          <ArrowLeft size={13} /> Knowledge Bases
        </Link>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">
            {kb?.name ?? "…"}
          </h1>
          {kb?.config?.locale && (
            <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium uppercase text-slate-500">
              <Globe size={11} /> {kb.config.locale}
            </span>
          )}
        </div>
        {kb && <KbDescription kb={kb} onUpdated={setKb} />}
      </div>

      <div className="mb-4 flex gap-1 border-b border-slate-200">
        {(
          [
            { id: "documents", label: "Documents", icon: FileText },
            { id: "chat", label: "Chat", icon: MessageSquareText },
            { id: "review", label: "Review", icon: AlertTriangle },
          ] as const
        ).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-sm font-medium transition-colors ${
              tab === id
                ? "border-indigo-600 text-indigo-700"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            <Icon size={15} /> {label}
            {id === "review" && reviewCount > 0 && (
              <span className="ml-0.5 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
                {reviewCount}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1">
        {tab === "documents" ? (
          <DocumentsPanel kbId={kbId} />
        ) : tab === "chat" ? (
          <ChatPanel kbId={kbId} allKbs={allKbs} />
        ) : (
          <ReviewPanel kbId={kbId} onCount={setReviewCount} />
        )}
      </div>
    </div>
  );
}
