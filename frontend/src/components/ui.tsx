import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  ShieldCheck,
  X,
} from "lucide-react";
import type { Severity } from "../types";
import { priorityLabels, statusLabel } from "../utils/labels";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand">
      <span className="brand-symbol">
        <ShieldCheck size={24} strokeWidth={1.7} />
      </span>
      {!compact && (
        <span>
          Sentinel<span className="brand-x">X</span>
          <small>Know what needs attention</small>
        </span>
      )}
    </div>
  );
}
export function Badge({
  value,
  severity = false,
}: {
  value: string;
  severity?: boolean;
}) {
  return (
    <span
      className={`badge ${severity ? `severity-${value}` : `status-${value}`}`}
    >
      <span className="badge-dot" />
      {severity ? priorityLabels[value as Severity] ?? humanize(value) : statusLabel(value)}
    </span>
  );
}
export function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/^./, (char) => char.toUpperCase());
}
export function time(value: string, full = false) {
  return new Date(value).toLocaleString(
    undefined,
    full
      ? {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }
      : {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        },
  );
}
export function relative(value: string) {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / 60000),
  );
  return minutes < 1
    ? "Just now"
    : minutes < 60
      ? `${minutes} ${minutes === 1 ? "minute" : "minutes"} ago`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)} ${Math.floor(minutes / 60) === 1 ? "hour" : "hours"} ago`
        : `${Math.floor(minutes / 1440)} ${Math.floor(minutes / 1440) === 1 ? "day" : "days"} ago`;
}
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </div>
  );
}
export function Loading({
  label = "Loading activity…",
}: {
  label?: string;
}) {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={19} className="spin" />
      {label}
    </div>
  );
}
export function Empty({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <ShieldCheck size={32} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function ErrorBox({
  message,
  retry,
}: {
  message: string | null;
  retry?: () => void;
}) {
  if (!message) return null;
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={17} />
      <span>{message}</span>
      {retry && (
        <button className="text-button" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
export function Pagination({
  total,
  offset,
  setOffset,
  size = 25,
}: {
  total: number;
  offset: number;
  setOffset: (value: number) => void;
  size?: number;
}) {
  return (
    <div className="pagination">
      <span>
        {total
          ? `${offset + 1}–${Math.min(offset + size, total)} of ${total.toLocaleString()}`
          : "0 results"}
      </span>
      <div>
        <button
          className="icon-button"
          aria-label="Previous page"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - size))}
        >
          <ChevronLeft size={17} />
        </button>
        <button
          className="icon-button"
          aria-label="Next page"
          disabled={offset + size >= total}
          onClick={() => setOffset(offset + size)}
        >
          <ChevronRight size={17} />
        </button>
      </div>
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
  drawer = false,
  initialFocus,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  drawer?: boolean;
  initialFocus?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const focusable = () =>
      Array.from(
        ref.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], summary, [tabindex="0"]',
        ) ?? [],
      ).filter((element) => element.getClientRects().length > 0);
    const preferred = initialFocus ? ref.current?.querySelector<HTMLElement>(initialFocus) : null;
    (preferred ?? focusable()[0])?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") closeRef.current();
      if (event.key === "Tab") {
        const elements = focusable();
        const first = elements[0],
          last = elements.at(-1);
        if (!ref.current?.contains(document.activeElement)) {
          event.preventDefault();
          (event.shiftKey ? last : first)?.focus();
          return;
        }
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", keydown);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", keydown);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [initialFocus]);
  return (
    <div
      className={`modal-backdrop ${drawer ? "drawer-backdrop" : ""}`}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        className={`modal ${wide ? "modal-wide" : ""} ${drawer ? "drawer" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

const ToastContext = createContext<(message: string, error?: boolean) => void>(
  () => {},
);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<
    { id: number; message: string; error: boolean }[]
  >([]);
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);
  function notify(message: string, error = false) {
    const id = Date.now() + Math.random();
    setToasts((items) => [...items.slice(-3), { id, message, error }]);
    timers.current.push(
      window.setTimeout(
        () => setToasts((items) => items.filter((item) => item.id !== id)),
        6000,
      ),
    );
  }
  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((item) => (
          <div
            key={item.id}
            className={`toast ${item.error ? "toast-error" : ""}`}
          >
            {item.error ? <AlertCircle size={17} /> : <Check size={17} />}
            <span>{item.message}</span>
            <button
              className="icon-button"
              aria-label="Dismiss notification"
              onClick={() =>
                setToasts((items) =>
                  items.filter((toast) => toast.id !== item.id),
                )
              }
            >
              <X size={15} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
export function useToast() {
  return useContext(ToastContext);
}
export const severities: Severity[] = ["critical", "high", "medium", "low"];
export function SeveritySelect({
  value,
  onChange,
  all = false,
}: {
  value: string;
  onChange: (value: string) => void;
  all?: boolean;
}) {
  return (
    <select
      aria-label="Priority"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      {all && <option value="">All priorities</option>}
      {severities.map((item) => (
        <option key={item} value={item}>
          {priorityLabels[item]}
        </option>
      ))}
    </select>
  );
}
