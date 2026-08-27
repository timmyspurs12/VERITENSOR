/**
 * VERITENSOR wordmark. Inline SVG (no external asset, renders in sandboxed
 * previews). The mark is a verification tick fused with a node lattice:
 * verification · intelligence · network · precision.
 */
export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="7.5" stroke="#2A323D" />
      <path d="M8 16.4L13.6 22L24 10.5" stroke="#7DD6FA" strokeWidth="2.1"
        strokeLinecap="square" />
      <circle cx="8" cy="16.4" r="2.1" fill="#0A0C10" stroke="#7DD6FA" strokeWidth="1.3" />
      <circle cx="24" cy="10.5" r="2.1" fill="#0A0C10" stroke="#A8F0C6" strokeWidth="1.3" />
      <circle cx="13.6" cy="22" r="1.5" fill="#7DD6FA" />
    </svg>
  );
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <Mark />
      {!compact && (
        <span className="font-mono text-[15px] font-semibold tracking-[0.16em] text-ink-1">
          VERITENSOR
        </span>
      )}
    </span>
  );
}
