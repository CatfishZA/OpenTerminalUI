export type VerificationMode = "RESEARCH" | "VERIFIED";

type Props = {
  value: VerificationMode;
  onChange: (mode: VerificationMode) => void;
};

const MODES: Array<{ value: VerificationMode; label: string; description: string }> = [
  { value: "RESEARCH", label: "Research", description: "Fast exploratory workflow. May use legacy/provider fallbacks." },
  { value: "VERIFIED", label: "Verified", description: "Reproducible daily simulation using persisted versioned data, with no synthetic or market fallback." },
];

export function VerificationModeControl({ value, onChange }: Props) {
  return (
    <fieldset className="rounded border border-terminal-border/60 bg-terminal-bg/60 p-2">
      <legend className="px-1 text-[11px] font-semibold uppercase tracking-wide text-terminal-accent">Execution Mode</legend>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Execution mode">
        {MODES.map((mode) => {
          const selected = value === mode.value;
          return (
            <button
              key={mode.value}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(mode.value)}
              className={`min-w-32 rounded border px-3 py-1.5 text-left focus:outline-none focus:ring-2 focus:ring-terminal-accent ${selected ? "border-terminal-accent bg-terminal-accent/15 text-terminal-accent" : "border-terminal-border text-terminal-muted hover:bg-terminal-border/20"}`}
            >
              <span className="block text-xs font-semibold uppercase">{mode.label}</span>
              <span className="mt-0.5 block max-w-72 text-[10px] leading-4">{mode.description}</span>
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[10px] text-terminal-muted">RESEARCH = exploratory · VERIFIED = reproducible, versioned, and deterministic</p>
    </fieldset>
  );
}
