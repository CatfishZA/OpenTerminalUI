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
        ["Verification", "VERIFIED"], ["Backtest Run", legacyRunId],
        ["Manifest Hash", <HashValue value={result.manifest_hash} />], ["Result Hash", <HashValue value={result.result_hash} />],
        ["Currency", currency], ["Settlement", "T+1"],
        ["Commission", `${commissionBps} bps`], ["Slippage", `${slippageBps} bps`], ["Data Quality", dataQuality],
      ]
    : [["Verification", "RESEARCH"], ["Run", legacyRunId]];
  return (
    <details aria-label="Run provenance" className="rounded-lg border border-terminal-border/60 bg-terminal-panel">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 marker:hidden">
        <span><span className="text-sm font-medium text-terminal-text">Run details</span>{verified ? <span className="ml-2 inline-flex flex-wrap gap-1 text-xs text-terminal-muted"><span>{shown(result.simulation_run_id)}</span><span aria-hidden="true">·</span><span>{shown(result.data_version_id)}</span><span aria-hidden="true">·</span><span>{shown(result.engine_version)}</span><span aria-hidden="true">·</span><span>{shown(result.daily_bar_path_policy)}</span></span> : <span className="ml-2 text-xs text-terminal-muted">Legacy research engine</span>}</span>
        <span className={`rounded border px-2 py-0.5 text-[10px] font-semibold ${verified ? "border-terminal-pos text-terminal-pos" : "border-terminal-warning text-terminal-warning"}`}>{verified ? "VERIFIED" : "RESEARCH"}</span>
      </summary>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 border-t border-terminal-border p-4 text-[11px] sm:grid-cols-2 lg:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={String(label)} className="grid min-w-0 grid-cols-[7rem_1fr] gap-2 border-b border-terminal-border/30 py-1">
            <dt className="text-terminal-muted">{label}</dt>
            <dd className="min-w-0 break-all text-terminal-text">{typeof value === "string" || value === undefined ? shown(value) : value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
