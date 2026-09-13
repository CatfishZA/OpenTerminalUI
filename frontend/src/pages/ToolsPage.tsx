import { ArrowRightIcon } from "@heroicons/react/24/outline";
import { Link } from "react-router-dom";

const GROUPS = [
  {
    title: "Trading tools",
    description: "Plan, execute, and review workflows without crowding the primary navigation.",
    items: [
      ["Position Sizer", "/equity/position-sizer"],
      ["Trade Journal", "/equity/journal"],
      ["Chart Workstation", "/equity/chart-workstation"],
      ["Market Depth", "/equity/dom"],
      ["Time & Sales", "/equity/tape"],
      ["OMS & Compliance", "/equity/oms"],
    ],
  },
  {
    title: "Analysis tools",
    description: "Focused research, comparison, and portfolio utilities.",
    items: [
      ["Model Lab", "/backtesting/model-lab"],
      ["Portfolio Lab", "/equity/portfolio/lab"],
      ["Statistical Lab", "/equity/stat-lab"],
      ["Pair Trading", "/equity/pair-trading"],
      ["Portfolio Optimizer", "/backtesting/portfolio-optimizer"],
      ["Compare", "/equity/compare"],
      ["Yield Curve", "/equity/yield-curve"],
      ["Options Greeks", "/equity/option-greeks"],
    ],
  },
  {
    title: "Workspace & operations",
    description: "Advanced configuration and operational surfaces remain one click away.",
    items: [
      ["Saved Views", "/equity/saved-views"],
      ["Launchpad", "/equity/launchpad"],
      ["Plugins", "/equity/plugins"],
      ["Data Quality", "/equity/data-quality"],
      ["Operations", "/equity/ops"],
      ["Reports", "/reports"],
    ],
  },
] as const;

export function ToolsPage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-8 p-5 md:p-8" aria-labelledby="tools-title">
      <header>
        <p className="text-sm font-medium text-terminal-accent">Workspace</p>
        <h1 id="tools-title" className="mt-1 text-2xl font-semibold text-terminal-text">Tools</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-terminal-muted">
          Every specialist capability remains available here, grouped by the job it helps you complete.
        </p>
      </header>

      <div className="grid gap-5 xl:grid-cols-3">
        {GROUPS.map((group) => (
          <section key={group.title} className="rounded-lg border border-terminal-border bg-terminal-panel p-5">
            <h2 className="text-base font-semibold text-terminal-text">{group.title}</h2>
            <p className="mt-1 min-h-10 text-sm leading-5 text-terminal-muted">{group.description}</p>
            <div className="mt-5 divide-y divide-terminal-border/70">
              {group.items.map(([label, to]) => (
                <Link key={to} to={to} className="group flex items-center justify-between py-3 text-sm text-terminal-text hover:text-terminal-accent">
                  {label}
                  <ArrowRightIcon className="h-4 w-4 text-terminal-muted transition-transform group-hover:translate-x-0.5 group-hover:text-terminal-accent" />
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}
