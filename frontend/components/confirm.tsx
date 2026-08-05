"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Button, Portal, useDialog } from "@/components/ui";

export type ConfirmOptions = {
  title: string;
  /** What actually happens, in plain terms. Say what is destroyed and what
   *  survives — a user deciding needs the second half as much as the first. */
  message: string;
  /** Names the action, matching the button that opened it ("Delete", not "OK"),
   *  so the wording stays the same from trigger to confirmation. */
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
};

type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

let show: ((p: Pending) => void) | null = null;

/** Drop-in for `window.confirm`, minus the browser chrome: same one-line call
 *  shape at the call site (`if (!(await confirm({…}))) return;`), but themed,
 *  keyboard-trapped and able to explain itself in more than one sentence.
 *  Falls back to the native dialog if the host isn't mounted. */
export function confirm(options: ConfirmOptions): Promise<boolean> {
  if (!show) return Promise.resolve(window.confirm(options.message));
  return new Promise<boolean>((resolve) => show!({ ...options, resolve }));
}

/** Mounted once, at the app root. */
export function ConfirmHost() {
  const [pending, setPending] = useState<Pending | null>(null);

  useEffect(() => {
    show = setPending;
    return () => {
      if (show === setPending) show = null;
    };
  }, []);

  const settle = useCallback(
    (ok: boolean) => {
      pending?.resolve(ok);
      setPending(null);
    },
    [pending],
  );

  const dismiss = useCallback(() => settle(false), [settle]);

  if (!pending) return null;
  return <ConfirmDialog pending={pending} onSettle={settle} onDismiss={dismiss} />;
}

function ConfirmDialog({
  pending,
  onSettle,
  onDismiss,
}: {
  pending: Pending;
  onSettle: (ok: boolean) => void;
  onDismiss: () => void;
}) {
  const ref = useDialog(onDismiss);
  const danger = pending.danger ?? true;

  return (
    <Portal>
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center bg-slate-900/50 p-0 backdrop-blur-[1px] sm:items-center sm:p-4"
      onClick={onDismiss}
    >
      <div
        ref={ref}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-body"
        className="w-full rounded-t-2xl bg-surface p-5 text-ink shadow-xl sm:max-w-md sm:rounded-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex gap-3">
          {danger && (
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-400"
              aria-hidden="true"
            >
              <AlertTriangle size={16} />
            </span>
          )}
          <div className="min-w-0">
            <h3 id="confirm-title" className="text-base font-semibold">
              {pending.title}
            </h3>
            <p
              id="confirm-body"
              className="mt-1 text-sm leading-6 text-ink-muted"
            >
              {pending.message}
            </p>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => onSettle(false)}>
            {pending.cancelLabel ?? "Cancel"}
          </Button>
          <Button
            variant={danger ? "danger" : "primary"}
            onClick={() => onSettle(true)}
          >
            {pending.confirmLabel ?? "Confirm"}
          </Button>
        </div>
      </div>
    </div>
    </Portal>
  );
}
