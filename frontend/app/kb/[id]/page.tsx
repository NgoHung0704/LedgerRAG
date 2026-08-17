"use client";

import { useT } from "@/components/LocaleProvider";
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
import KbSettings from "@/components/KbSettings";
import ReviewPanel from "@/components/ReviewPanel";

type Tab = "documents" | "chat" | "review";

export default function KBPage({ params }: { params: { id: string } }) {
  const t = useT();
  const kbId = params.id;
  const [kb, setKb] = useState<KB | null>(null);
  const [allKbs, setAllKbs] = useState<KB[]>([]);
  const [tab, setTab] = useState<Tab>("documents");
  const [reviewCount, setReviewCount] = useState(0);
  // the list's ⋮ t("kb.settings_rename") lands here with ?settings=1 so the panel
  // opens straight away; strip the param so a refresh doesn't reopen it
  const [openSettings, setOpenSettings] = useState(false);

  useEffect(() => {
    getKb(kbId).then(setKb).catch(() => {});
    getKbs().then(setAllKbs).catch(() => {});
    getNeedsReview(kbId)
      .then((r) => setReviewCount(r.count))
      .catch(() => {});
  }, [kbId]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("settings") === "1") {
      setOpenSettings(true);
      url.searchParams.delete("settings");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  return (
    <div className="flex h-full flex-col">
      {/* name, settings and the tabs stay put while the list scrolls: negative
          margins cover the container's padding so nothing shows behind it */}
      <div className="sticky top-0 z-20 -mx-4 -mt-5 mb-4 border-b border-line bg-canvas/95 px-4 pt-5 backdrop-blur sm:-mx-6 sm:-mt-6 sm:px-6 sm:pt-6">
        <Link
          href="/"
          className="mb-2 inline-flex items-center gap-1 text-xs text-ink-subtle hover:text-ink-muted"
        >
          <ArrowLeft size={13} /> {t("kb.breadcrumb")}
        </Link>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">
            {kb?.name ?? "…"}
          </h1>
          {kb?.config?.locale && (
            <span className="inline-flex items-center gap-1 rounded-full bg-surface-sunken px-2 py-0.5 text-[11px] font-medium uppercase text-ink-muted">
              <Globe size={11} /> {kb.config.locale}
            </span>
          )}
          {kb && (
            <div className="ml-auto">
              <KbSettings kb={kb} onUpdated={setKb} defaultOpen={openSettings} />
            </div>
          )}
        </div>
        {kb && <KbDescription kb={kb} />}

        <div className="-mb-px mt-3 flex gap-1">
          {(
            [
              { id: "documents", label: t("kb.tab_documents"), icon: FileText },
              { id: "chat", label: t("kb.tab_chat"), icon: MessageSquareText },
              { id: "review", label: t("kb.tab_review"), icon: AlertTriangle },
            ] as const
          ).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`inline-flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-sm font-medium transition-colors ${
                tab === id
                  ? "border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300"
                  : "border-transparent text-ink-muted hover:text-ink"
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
