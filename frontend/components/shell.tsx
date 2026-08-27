"use client";

import clsx from "clsx";
import {
  Activity, BarChart3, Boxes, Cpu, FlaskConical, Gauge, Layers, LineChart,
  Menu, Network, PlayCircle, ScrollText, Server, Sparkles, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";
import { ModeBanner } from "@/components/mode-banner";
import { Wordmark } from "@/components/wordmark";

const NAV = [
  { group: "Network", items: [
    { href: "/dashboard", label: "Overview", icon: Gauge },
    { href: "/live", label: "Live verification", icon: Activity },
    { href: "/graph", label: "Network graph", icon: Network },
  ]},
  { group: "Participants", items: [
    { href: "/miners", label: "Miner leaderboard", icon: Cpu },
    { href: "/validators", label: "Validators", icon: Server },
  ]},
  { group: "Verification", items: [
    { href: "/tasks", label: "Task explorer", icon: Layers },
    { href: "/scores", label: "Score explorer", icon: BarChart3 },
    { href: "/emissions", label: "Emissions", icon: LineChart },
  ]},
  { group: "Mechanism", items: [
    { href: "/mechanism", label: "How it works", icon: Boxes },
    { href: "/simulation", label: "Network simulation", icon: FlaskConical },
    { href: "/demo", label: "Hackathon demo", icon: PlayCircle },
    { href: "/admin", label: "Diagnostics", icon: ScrollText },
  ]},
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = React.useState(false);
  const isLanding = pathname === "/";

  React.useEffect(() => setOpen(false), [pathname]);

  if (isLanding) return <>{children}</>;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur-md">
        <div className="flex h-14 items-center gap-3 px-4 md:px-6">
          <button
            className="rounded-sm border border-line-strong p-1.5 text-ink-2 lg:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-label="Toggle navigation"
          >
            {open ? <X size={15} /> : <Menu size={15} />}
          </button>
          <Link href="/" className="shrink-0"><Wordmark /></Link>
          <span className="hidden rounded-xs border border-line-strong px-1.5 py-0.5 font-mono text-2xs tracking-[0.1em] text-ink-3 sm:inline">
            SUBNET PROTOTYPE
          </span>
          <nav className="ml-auto hidden items-center gap-1 md:flex">
            <Link href="/demo"
              className="flex items-center gap-1.5 rounded-sm border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20">
              <Sparkles size={13} /> Run full demo
            </Link>
          </nav>
        </div>
        <ModeBanner />
      </header>

      <div className="flex flex-1">
        <aside className={clsx(
          "fixed inset-y-0 left-0 z-40 w-64 shrink-0 overflow-y-auto border-r border-line bg-surface-1 px-3 pb-8 pt-4 transition-transform lg:sticky lg:top-[89px] lg:z-0 lg:h-[calc(100vh-89px)] lg:translate-x-0 lg:bg-bg-subtle",
          open ? "translate-x-0" : "-translate-x-full")}>
          <div className="mb-4 flex items-center justify-between lg:hidden">
            <Wordmark />
            <button onClick={() => setOpen(false)} aria-label="Close navigation">
              <X size={16} className="text-ink-3" />
            </button>
          </div>
          {NAV.map((group) => (
            <div key={group.group} className="mb-5">
              <p className="px-2.5 pb-1.5 font-mono text-2xs uppercase tracking-[0.14em] text-ink-3">
                {group.group}
              </p>
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const active = pathname === item.href || pathname.startsWith(item.href + "/");
                  const Icon = item.icon;
                  return (
                    <Link key={item.href} href={item.href}
                      className={clsx(
                        "flex items-center gap-2.5 rounded-sm px-2.5 py-2 text-[13px] transition-colors",
                        active
                          ? "bg-accent/10 text-accent"
                          : "text-ink-2 hover:bg-surface-2 hover:text-ink-1")}>
                      <Icon size={14} className={active ? "text-accent" : "text-ink-3"} />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
          <p className="px-2.5 text-2xs leading-relaxed text-ink-3">
            Prototype for the Bittensor Global Subnet Hackathon 2026. Not
            affiliated with or endorsed by the Opentensor Foundation.
          </p>
        </aside>

        {open && (
          <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setOpen(false)} />
        )}

        <main className="min-w-0 flex-1 px-4 py-6 md:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({
  title, description, actions,
}: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-ink-1">{title}</h1>
        {description && (
          <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-ink-2">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
