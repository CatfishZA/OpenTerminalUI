import { useEffect, useState, type ComponentType } from "react";
import {
  BeakerIcon,
  BriefcaseIcon,
  ChartBarIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  CircleStackIcon,
  Cog6ToothIcon,
  HomeIcon,
  NewspaperIcon,
  PresentationChartLineIcon,
  ShieldCheckIcon,
  Squares2X2Icon,
  WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";
import { NavLink } from "react-router-dom";

type NavItem = {
  label: string;
  to: string;
  icon: ComponentType<{ className?: string }>;
  aliases?: string[];
};

const PRIMARY_ITEMS: NavItem[] = [
  { label: "Home", to: "/home", icon: HomeIcon },
  { label: "Markets", to: "/equity/stocks", icon: PresentationChartLineIcon, aliases: ["/equity/security", "/equity/commodities", "/equity/forex", "/fno"] },
  { label: "Research", to: "/equity/research", icon: BeakerIcon, aliases: ["/equity/screener", "/equity/factors", "/equity/alpha-zoo"] },
  { label: "Backtest", to: "/backtesting", icon: ChartBarIcon },
  { label: "Paper", to: "/equity/paper", icon: NewspaperIcon },
  { label: "Portfolio", to: "/equity/portfolio", icon: BriefcaseIcon },
];

const SECONDARY_ITEMS: NavItem[] = [
  { label: "Risk", to: "/equity/risk", icon: ShieldCheckIcon, aliases: ["/equity/correlation"] },
  { label: "Data", to: "/equity/data-quality", icon: CircleStackIcon, aliases: ["/equity/ops"] },
  { label: "Tools", to: "/equity/tools", icon: WrenchScrewdriverIcon, aliases: ["/equity/position-sizer", "/equity/journal", "/equity/chart-workstation"] },
  { label: "Settings", to: "/equity/settings", icon: Cog6ToothIcon, aliases: ["/account"] },
];

const COLLAPSE_STORAGE_KEY = "ot:shell:sidebar-collapsed:v1";

function NavGroup({ items, collapsed }: { items: NavItem[]; collapsed: boolean }) {
  return (
    <div className="space-y-1">
      {items.map(({ label, to, icon: Icon, aliases = [] }) => (
        <NavLink
          key={to}
          to={to}
          title={collapsed ? label : undefined}
          className={({ isActive }) => {
            const routeActive = isActive || aliases.some((path) => window.location.pathname.startsWith(path));
            return [
              "group flex h-10 items-center gap-3 rounded-md border px-3 text-sm transition-colors",
              routeActive
                ? "border-terminal-accent/35 bg-terminal-accent/10 text-terminal-text"
                : "border-transparent text-terminal-muted hover:bg-terminal-panel-hover hover:text-terminal-text",
              collapsed ? "justify-center px-0" : "",
            ].join(" ");
          }}
        >
          {({ isActive }) => {
            const routeActive = isActive || aliases.some((path) => window.location.pathname.startsWith(path));
            return (
              <>
                <Icon className={`h-5 w-5 shrink-0 ${routeActive ? "text-terminal-accent" : "text-terminal-muted group-hover:text-terminal-text"}`} />
                {!collapsed ? <span className="truncate font-medium">{label}</span> : null}
              </>
            );
          }}
        </NavLink>
      ))}
    </div>
  );
}

export function PrimarySidebar() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSE_STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSE_STORAGE_KEY, String(collapsed));
    } catch {
      // Sidebar remains usable when storage is unavailable.
    }
  }, [collapsed]);

  return (
    <aside
      className={`hidden h-screen shrink-0 flex-col border-r border-terminal-border bg-terminal-panel/95 px-3 py-4 transition-[width] md:flex ${collapsed ? "w-[72px]" : "w-[216px]"}`}
      aria-label="Primary navigation"
    >
      <NavLink to="/home" className={`mb-7 flex h-9 items-center gap-3 px-2 ${collapsed ? "justify-center" : ""}`}>
        <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-terminal-accent text-sm font-bold text-black">OT</span>
        {!collapsed ? (
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-terminal-text">OpenTerminal</span>
            <span className="block text-[11px] text-terminal-muted">Investment workspace</span>
          </span>
        ) : null}
      </NavLink>

      <nav className="flex min-h-0 flex-1 flex-col" aria-label="Product areas">
        <NavGroup items={PRIMARY_ITEMS} collapsed={collapsed} />
        <div className="my-4 border-t border-terminal-border/70" />
        {!collapsed ? <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-terminal-muted">Workspace</p> : null}
        <NavGroup items={SECONDARY_ITEMS} collapsed={collapsed} />
      </nav>

      <button
        type="button"
        onClick={() => setCollapsed((value) => !value)}
        className="mt-3 flex h-9 items-center justify-center gap-2 rounded-md border border-terminal-border text-xs text-terminal-muted hover:border-terminal-border-strong hover:text-terminal-text"
        aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        aria-expanded={!collapsed}
      >
        {collapsed ? <ChevronDoubleRightIcon className="h-4 w-4" /> : <ChevronDoubleLeftIcon className="h-4 w-4" />}
        {!collapsed ? "Collapse" : null}
      </button>
    </aside>
  );
}
