"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, Loader2, X } from "lucide-react";
import type { Doc } from "@/lib/api";

export function Button({
  children,
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
}) {
  const styles = {
    // disabled dims the whole button rather than just lightening its fill, so
    // it reads as "not available yet" instead of as a different kind of button
    primary: "bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-45",
    secondary:
      "border border-line-strong bg-surface text-ink hover:bg-surface-sunken disabled:opacity-50",
    ghost: "text-ink-muted hover:bg-surface-sunken hover:text-ink disabled:opacity-50",
    // destructive actions read as destructive before they are pressed, rather
    // than being a secondary button with the label doing all the warning
    danger:
      "border border-red-300 bg-surface text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/70 dark:text-red-400 dark:hover:bg-red-950/40",
  }[variant];
  // min-h keeps every button a comfortable target even when a caller trims the
  // padding to fit a toolbar
  const sizes = { sm: "min-h-8 px-2.5 py-1 text-xs", md: "min-h-9 px-3.5 py-2 text-sm" }[size];
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${sizes} ${styles} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

/** An icon-only control. `label` is mandatory: without it the button is silent
 *  to a screen reader and unlabelled on hover, which is the single most common
 *  way an icon button goes wrong. The `after:` inset grows the hit area to a
 *  finger-sized target without changing how the button lays out. */
export function IconButton({
  label,
  children,
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`relative inline-flex h-8 w-8 items-center justify-center rounded-lg text-ink-muted transition-colors after:absolute after:-inset-1.5 after:content-[''] hover:bg-surface-sunken hover:text-ink disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Card({
  children,
  className = "",
  id,
}: {
  children: React.ReactNode;
  className?: string;
  /** so a card can be an anchor target — Review links straight to one */
  id?: string;
}) {
  return (
    <div
      id={id}
      className={`rounded-xl border border-line bg-surface shadow-card ${className}`}
    >
      {children}
    </div>
  );
}

export function Spinner({ size = 16, label }: { size?: number; label?: string }) {
  return (
    <>
      <Loader2
        size={size}
        data-spinner
        aria-hidden="true"
        className="animate-spin text-ink-faint"
      />
      {/* announced to screen readers, which otherwise get no sign that the
          screen is waiting on anything */}
      <span role="status" className="sr-only">
        {label ?? "Loading…"}
      </span>
    </>
  );
}

// Colour alone can't carry the state (colour-blind users, greyscale printouts),
// so each status also gets its own icon and its own word.
const STATUS_STYLES: Record<
  Doc["status"],
  { cls: string; icon: React.ReactNode; pulse: boolean }
> = {
  queued: {
    cls: "bg-surface-sunken text-ink-muted ring-1 ring-line",
    icon: <Clock size={11} />,
    pulse: false,
  },
  parsing: {
    cls: "bg-amber-50 text-amber-800 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-900",
    icon: null,
    pulse: true,
  },
  indexing: {
    cls: "bg-blue-50 text-blue-800 ring-1 ring-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:ring-blue-900",
    icon: null,
    pulse: true,
  },
  done: {
    cls: "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900",
    icon: <CheckCircle2 size={11} />,
    pulse: false,
  },
  failed: {
    cls: "bg-red-50 text-red-800 ring-1 ring-red-200 dark:bg-red-950/40 dark:text-red-300 dark:ring-red-900",
    icon: <AlertTriangle size={11} />,
    pulse: false,
  },
};

export function StatusPill({ status }: { status: Doc["status"] }) {
  const { cls, icon, pulse } = STATUS_STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {pulse && (
        <span className="relative flex h-1.5 w-1.5" aria-hidden="true">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
        </span>
      )}
      {icon}
      {status}
    </span>
  );
}

/** Keeps Tab inside the dialog, sends Escape to `onClose`, and hands focus back
 *  to whatever opened it. Without this a keyboard user tabs straight out of an
 *  open dialog into the page behind it and cannot find their way back. */
export function useDialog(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  // Captured during render, which is BEFORE React commits an `autoFocus` — by
  // the time the effect below runs, activeElement is already the focused field
  // inside the dialog, and restoring to that on close would drop focus to the
  // body.
  const [opener] = useState<HTMLElement | null>(() =>
    typeof document === "undefined"
      ? null
      : (document.activeElement as HTMLElement | null),
  );

  const focusables = useCallback(
    () =>
      Array.from(
        ref.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => el.offsetParent !== null),
    [],
  );

  useEffect(() => {
    // the page behind must not scroll under the dialog
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // React's `autoFocus` has already run by now, so if focus is inside the
    // dialog it was put there deliberately — leave it. Landing on the close
    // button when there is a form to fill in makes a dialog feel like it
    // opened on its way out.
    if (!ref.current?.contains(document.activeElement)) {
      (focusables()[0] ?? ref.current)?.focus();
    }

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const [start, end] = [items[0], items[items.length - 1]];
      if (e.shiftKey && document.activeElement === start) {
        e.preventDefault();
        end.focus();
      } else if (!e.shiftKey && document.activeElement === end) {
        e.preventDefault();
        start.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      // only if it is still on the page — a dialog opened from a row's button
      // may well have deleted that row
      if (opener?.isConnected) opener.focus?.();
    };
  }, [onClose, focusables, opener]);

  return ref;
}

export function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const ref = useDialog(onClose);
  const titleId = `dlg-${title.replace(/\W+/g, "-").toLowerCase()}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 backdrop-blur-[1px] sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`max-h-[90vh] w-full ${wide ? "sm:max-w-3xl" : "sm:max-w-md"} overflow-y-auto rounded-t-2xl bg-surface p-5 text-ink shadow-xl sm:max-h-[85vh] sm:rounded-xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <h3 id={titleId} className="text-base font-semibold">
            {title}
          </h3>
          <IconButton label="Close" onClick={onClose}>
            <X size={18} />
          </IconButton>
        </div>
        {children}
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  hint: string;
  /** an empty screen is an invitation to act — give it the action when there
   *  is an obvious one */
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line-strong bg-surface px-6 py-14 text-center">
      <div className="mb-3 text-ink-faint" aria-hidden="true">
        {icon}
      </div>
      <div className="text-sm font-medium text-ink">{title}</div>
      <div className="mt-1 max-w-sm text-xs leading-5 text-ink-subtle">{hint}</div>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** A labelled form control. The `<label>` WRAPS the input, which associates the
 *  two without needing an id on either — so clicking the label focuses the
 *  field and a screen reader reads the two together. `hint` sits under the
 *  control: it explains, it never doubles as the label. */
export function Field({
  label,
  hint,
  children,
  className = "",
}: {
  label: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-xs font-medium text-ink-muted">
        {label}
      </span>
      {children}
      {hint && (
        <span className="mt-1 block text-[11px] leading-4 text-ink-subtle">
          {hint}
        </span>
      )}
    </label>
  );
}

export const inputCls =
  "w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30";
