import type { BacktestJobResult } from "../../api/client";

type Props = {
  legacyRunId: string;
  result: NonNullable<BacktestJobResult["result"]>;
  currency: string;
  commissionBps: number;
  slippageBps: number;
};

const shown = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
};

function HashValue({ value }: { value?: string }) {
  const display = value && value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : shown(value);
  return <span className="font-mono" title={value}>{display}</span>;
}

export function RunProvenancePanel({ legacyRunId, result, currency, commissionBps, slippageBps }: Props) {
  const verified = result.verification_level === "VERIFIED";
  const dataQuality = result.data_quality && typeof result.data_quality === "object"
    ? shown((result.data_quality as Record<string, unknown>).status)
    : "—";
  const rows = verified
    ? [
        ["Verification", "VERIFIED"], ["Backtest Run", legacyRunId], ["Simulation Run", result.simulation_run_id],
        ["Data Version", result.data_version_id], ["Engine", result.engine_version],
        ["Manifest Hash", <HashValue value={result.manifest_hash} />], ["Result Hash", <HashValue value={result.result_hash} />],
        ["Bar Path Policy", result.daily_bar_path_policy], ["Currency", currency], ["Settlement", "T+1"],
        ["Commission", `${commissionBps} bps`], ["Slippage", `${slippageBps} bps`], ["Data Quality", dataQuality],
      ]
    : [["Verification", "RESEARCH"], ["Engine", "Legacy research engine"], ["Run", legacyRunId]];
  return (
    <section aria-label="Run provenance" className="rounded border border-terminal-border/60 bg-terminal-bg/60 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-terminal-text">Run Provenance</h3>
        <span className={`rounded border px-2 py-0.5 text-[10px] font-semibold ${verified ? "border-terminal-pos text-terminal-pos" : "border-terminal-warning text-terminal-warning"}`}>
          {verified ? "VERIFIED" : "RESEARCH"}
        </span>
      </div>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-[11px] sm:grid-cols-2 lg:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={String(label)} className="grid min-w-0 grid-cols-[7rem_1fr] gap-2 border-b border-terminal-border/30 py-1">
            <dt className="text-terminal-muted">{label}</dt>
            <dd className="min-w-0 break-all text-terminal-text">{typeof value === "string" || value === undefined ? shown(value) : value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
