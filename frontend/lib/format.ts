export const pct = (v: number | undefined, digits = 1): string =>
  v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(digits)}%`;

export const num = (v: number | undefined, digits = 3): string =>
  v === undefined || Number.isNaN(v) ? "—" : v.toFixed(digits);

export const ms = (v: number | undefined): string => {
  if (v === undefined || Number.isNaN(v)) return "—";
  return v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${Math.round(v)}ms`;
};

export const compact = (v: number): string =>
  new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(v);

export const timeAgo = (iso: string): string => {
  const delta = (Date.now() - new Date(iso).getTime()) / 1000;
  if (delta < 60) return `${Math.max(0, Math.round(delta))}s ago`;
  if (delta < 3600) return `${Math.round(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.round(delta / 3600)}h ago`;
  return `${Math.round(delta / 86400)}d ago`;
};

export const clock = (iso: string): string =>
  new Date(iso).toLocaleTimeString("en-GB", { hour12: false });

export const categoryLabel: Record<string, string> = {
  code: "Code Security",
  math: "Mathematics",
  reasoning: "Logical Reasoning",
  data: "Data Analysis",
};

export const categoryColor: Record<string, string> = {
  code: "#7DD6FA",
  math: "#A8F0C6",
  reasoning: "#EFC468",
  data: "#C9A7F0",
};
