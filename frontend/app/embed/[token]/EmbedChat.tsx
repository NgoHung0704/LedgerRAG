"use client";

import { useEffect, useState } from "react";

import ChatPanel from "@/components/ChatPanel";
import { getEmbedFace, type EmbedFace } from "@/lib/api";

/** One assistant, hosted by another application.
 *
 *  No rail, no navigation, nothing belonging to this product's own shell — the
 *  host page supplies the frame. What DOES travel is the answer surface: the
 *  caution notice, the verification badge, the inline source chips and the
 *  weighted source list. That is the reason this is an iframe rather than an
 *  API somebody re-renders. */
export default function EmbedChat({ token }: { token: string }) {
  const [face, setFace] = useState<EmbedFace | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getEmbedFace(token)
      .then(setFace)
      .catch(() => setFailed(true));
  }, [token]);

  if (failed)
    return (
      <div className="flex h-screen items-center justify-center p-6 text-center text-sm text-ink-muted">
        {/* deliberately says nothing about whether an assistant exists */}
        Not found.
      </div>
    );

  return (
    <div className="flex h-screen flex-col p-3">
      {face && (
        <div className="mb-2 shrink-0">
          <div className="text-sm font-semibold text-ink">{face.name}</div>
          {face.description && (
            <div className="text-xs text-ink-muted">{face.description}</div>
          )}
        </div>
      )}
      <div className="min-h-0 flex-1">
        <ChatPanel embedToken={token} allKbs={[]} />
      </div>
    </div>
  );
}
