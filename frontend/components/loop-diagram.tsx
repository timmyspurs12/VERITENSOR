"use client";

import clsx from "clsx";
import * as React from "react";

const STEPS = [
  { key: "task", label: "Task", detail: "Seeded generator produces a problem with hidden, computed ground truth." },
  { key: "miners", label: "Miners", detail: "Competing miners answer with confidence and evidence." },
  { key: "verification", label: "Verification", detail: "Deterministic verifier + adversarial mutation probe." },
  { key: "scoring", label: "Scoring", detail: "Accuracy, evidence, robustness, calibration, latency." },
  { key: "reputation", label: "Reputation", detail: "EMA smoothing with a minimum-sample trust ramp." },
  { key: "emissions", label: "Emissions", detail: "Normalised weights summing to 1, capped per miner." },
];

/** Interactive loop diagram. Hover/tap a stage to read what it does. */
export function LoopDiagram({ active }: { active?: string }) {
  const [hover, setHover] = React.useState<string | null>(null);
  const current = hover ?? active ?? null;

  return (
    <div>
      <div className="flex flex-wrap items-stretch gap-2">
        {STEPS.map((s, i) => (
          <React.Fragment key={s.key}>
            <button
              onMouseEnter={() => setHover(s.key)}
              onMouseLeave={() => setHover(null)}
              onClick={() => setHover(s.key)}
              className={clsx(
                "flex-1 basis-[130px] rounded-md border px-3 py-3 text-left transition-colors",
                current === s.key
                  ? "border-accent/45 bg-accent/10"
                  : "border-line bg-surface-1 hover:border-line-hi")}
            >
              <span className="font-mono text-2xs text-ink-3">{String(i + 1).padStart(2, "0")}</span>
              <p className={clsx("mt-1 text-[13px] font-medium",
                current === s.key ? "text-accent" : "text-ink-1")}>{s.label}</p>
            </button>
            {i < STEPS.length - 1 && (
              <div className="hidden shrink-0 items-center text-line-hi lg:flex">→</div>
            )}
          </React.Fragment>
        ))}
      </div>
      <div className="mt-3 rounded-md border border-line bg-surface-1 px-4 py-3 text-[13px] leading-relaxed text-ink-2">
        {current
          ? STEPS.find((s) => s.key === current)!.detail
          : "Better verified intelligence → higher reputation → higher emission weight → stronger miners. Hover a stage for detail."}
      </div>
    </div>
  );
}
