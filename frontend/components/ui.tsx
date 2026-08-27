"use client";

import clsx from "clsx";
import { AlertTriangle, Loader2 } from "lucide-react";
import * as React from "react";

/* ---------------------------------------------------------------- surface */
export function Card({
  className, children, ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...rest}
      className={clsx(
        "rounded-lg border border-line bg-surface-1 hairline",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title, subtitle, right, className,
}: {
  title: React.ReactNode; subtitle?: React.ReactNode;
  right?: React.ReactNode; className?: string;
}) {
  return (
    <div className={clsx("flex items-start justify-between gap-4 border-b border-line px-5 py-3.5", className)}>
      <div className="min-w-0">
        <h2 className="truncate text-[13px] font-semibold tracking-tight text-ink-1">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

/* ------------------------------------------------------------------ label */
export function Label({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={clsx("font-mono text-2xs uppercase tracking-[0.14em] text-ink-3", className)}>
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ badge */
const badgeTones = {
  neutral: "border-line-strong bg-surface-2 text-ink-2",
  accent: "border-accent/30 bg-accent/10 text-accent",
  positive: "border-positive/25 bg-positive/10 text-positive",
  warning: "border-warning/25 bg-warning/10 text-warning",
  negative: "border-negative/25 bg-negative/10 text-negative",
  mint: "border-mint/25 bg-mint/10 text-mint",
} as const;

export function Badge({
  children, tone = "neutral", className, mono = true,
}: {
  children: React.ReactNode; tone?: keyof typeof badgeTones;
  className?: string; mono?: boolean;
}) {
  return (
    <span className={clsx(
      "inline-flex items-center gap-1.5 whitespace-nowrap rounded-xs border px-1.5 py-0.5 text-2xs uppercase tracking-[0.1em]",
      mono && "font-mono", badgeTones[tone], className)}>
      {children}
    </span>
  );
}

/* ----------------------------------------------------------------- button */
export function Button({
  children, variant = "default", size = "md", className, ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "ghost" | "danger"; size?: "sm" | "md" | "lg";
}) {
  return (
    <button
      {...rest}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-sm border font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45",
        size === "sm" && "px-2.5 py-1 text-xs",
        size === "md" && "px-3.5 py-2 text-[13px]",
        size === "lg" && "px-5 py-2.5 text-sm",
        variant === "default" &&
          "border-line-strong bg-surface-2 text-ink-1 hover:border-line-hi hover:bg-surface-3",
        variant === "primary" &&
          "border-accent/40 bg-accent/15 text-accent hover:bg-accent/25",
        variant === "ghost" &&
          "border-transparent bg-transparent text-ink-2 hover:bg-surface-2 hover:text-ink-1",
        variant === "danger" &&
          "border-negative/30 bg-negative/10 text-negative hover:bg-negative/20",
        className,
      )}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ stats */
export function Stat({
  label, value, hint, tone = "default", loading,
}: {
  label: string; value: React.ReactNode; hint?: React.ReactNode;
  tone?: "default" | "accent" | "positive" | "warning"; loading?: boolean;
}) {
  return (
    <div className="min-w-0 px-5 py-4">
      <Label>{label}</Label>
      <div className={clsx(
        "tabular mt-1.5 truncate font-mono text-[26px] leading-none",
        tone === "accent" && "text-accent",
        tone === "positive" && "text-positive",
        tone === "warning" && "text-warning",
        tone === "default" && "text-ink-1")}>
        {loading ? <Skeleton className="h-6 w-20" /> : value}
      </div>
      {hint && <div className="mt-2 truncate text-xs text-ink-3">{hint}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ meter */
export function Meter({ value, tone = "accent", className }: {
  value: number; tone?: "accent" | "mint" | "warning" | "negative"; className?: string;
}) {
  const colour = { accent: "#7DD6FA", mint: "#A8F0C6", warning: "#EFC468", negative: "#F27E88" }[tone];
  return (
    <div className={clsx("h-1 w-full overflow-hidden rounded-full bg-surface-3", className)}>
      <div className="h-full rounded-full transition-all duration-500"
        style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: colour }} />
    </div>
  );
}

/* -------------------------------------------------------------- feedback  */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={clsx("relative overflow-hidden rounded-xs bg-surface-2", className)}>
      <div className="absolute inset-y-0 -left-1/3 w-1/3 animate-sweep bg-gradient-to-r from-transparent via-white/[0.045] to-transparent" />
    </div>
  );
}

export function LoadingRow({ label = "Loading subnet data" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 px-5 py-8 text-sm text-ink-3">
      <Loader2 size={14} className="animate-spin text-accent" />
      {label}…
    </div>
  );
}

export function EmptyState({
  title, description, action,
}: { title: string; description: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="rounded-md border border-line bg-surface-2 p-2.5">
        <AlertTriangle size={16} className="text-ink-3" />
      </div>
      <p className="text-sm font-medium text-ink-1">{title}</p>
      <p className="max-w-sm text-xs leading-relaxed text-ink-3">{description}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: string; retry?: () => void }) {
  return (
    <div className="m-5 rounded-md border border-negative/25 bg-negative/[0.06] px-4 py-3">
      <p className="text-xs font-medium text-negative">Backend unavailable</p>
      <p className="mt-1 font-mono text-2xs text-ink-3">{error}</p>
      {retry && (
        <Button size="sm" variant="ghost" className="mt-2" onClick={retry}>Retry</Button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ table */
export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={clsx("w-full border-collapse text-[13px]", className)}>{children}</table>
    </div>
  );
}

export function Th({ children, className, align = "left" }: {
  children?: React.ReactNode; className?: string; align?: "left" | "right" | "center";
}) {
  return (
    <th className={clsx(
      "sticky top-0 z-[1] whitespace-nowrap border-b border-line bg-surface-1 px-3 py-2.5 font-mono text-2xs font-medium uppercase tracking-[0.12em] text-ink-3",
      align === "right" && "text-right", align === "center" && "text-center",
      align === "left" && "text-left", className)}>
      {children}
    </th>
  );
}

export function Td({ children, className, align = "left" }: {
  children?: React.ReactNode; className?: string; align?: "left" | "right" | "center";
}) {
  return (
    <td className={clsx("border-b border-line/60 px-3 py-2.5 text-ink-2",
      align === "right" && "text-right tabular", align === "center" && "text-center",
      className)}>
      {children}
    </td>
  );
}

/* ----------------------------------------------------------------- inputs */
export function Select({
  label, value, onChange, options, className,
}: {
  label?: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[]; className?: string;
}) {
  return (
    <label className={clsx("flex items-center gap-2", className)}>
      {label && <Label>{label}</Label>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-sm border border-line-strong bg-surface-2 px-2 py-1.5 text-[13px] text-ink-1 outline-none focus:border-accent/50"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} className="bg-surface-2">{o.label}</option>
        ))}
      </select>
    </label>
  );
}

export function SegmentedControl<T extends string>({
  value, onChange, options, size = "md",
}: {
  value: T; onChange: (v: T) => void;
  options: { value: T; label: string }[]; size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex rounded-sm border border-line-strong bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "rounded-[3px] font-mono uppercase tracking-[0.1em] transition-colors",
            size === "sm" ? "px-2 py-1 text-2xs" : "px-2.5 py-1.5 text-2xs",
            value === o.value
              ? "bg-accent/15 text-accent"
              : "text-ink-3 hover:text-ink-1")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
