import { SparklesIcon } from "@heroicons/react/24/outline";

import { useAgentStore } from "../../agent/agentStore";
import { useAuth } from "../../contexts/AuthContext";
import { useQuotesStore } from "../../realtime/useQuotesStream";
import { NotificationBell } from "../notifications/NotificationBell";
import { CommandBar } from "./CommandBar";
import type { CommandExecutionResult } from "./commanding";

export function GlobalHeader({ onExecute }: { onExecute: (command: string) => Promise<CommandExecutionResult> | CommandExecutionResult }) {
  const { user } = useAuth();
  const marketStatus = useQuotesStore((state) => state.marketStatus) as { marketState?: Array<{ marketStatus?: string }> } | undefined;
  const setAgentOpen = useAgentStore((state) => state.setOpen);
  const status = String(marketStatus?.marketState?.[0]?.marketStatus || "connected").toLowerCase();
  const initials = (user?.email?.split("@")[0] || "user")
    .split(/[._-]+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <header className="relative z-40 flex min-h-[64px] items-center gap-3 border-b border-terminal-border bg-terminal-bg/95 pr-3 backdrop-blur" aria-label="Global header">
      <div className="min-w-0 flex-1">
        <CommandBar onExecute={onExecute} />
      </div>
      <div className="hidden items-center gap-2 lg:flex" aria-label="Market data status">
        <span className="h-2 w-2 rounded-full bg-terminal-pos" aria-hidden="true" />
        <span className="text-xs text-terminal-muted">Data {status}</span>
      </div>
      <button
        type="button"
        onClick={() => setAgentOpen(true)}
        className="hidden h-9 items-center gap-2 rounded-md border border-terminal-border px-3 text-xs text-terminal-muted hover:border-terminal-accent/45 hover:text-terminal-text sm:inline-flex"
        aria-label="Open AI assistant"
      >
        <SparklesIcon className="h-4 w-4 text-terminal-accent" />
        Ask AI
      </button>
      <NotificationBell />
      <a
        href="/account"
        className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-terminal-border bg-terminal-panel text-xs font-semibold text-terminal-text hover:border-terminal-accent/45"
        aria-label="Open profile"
        title={user?.email || "Account"}
      >
        {initials}
      </a>
    </header>
  );
}
