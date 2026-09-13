import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ErrorBoundary } from "../common/ErrorBoundary";
import { MobileBottomNav } from "./MobileBottomNav";
import { CommandPalette } from "./CommandPalette";
import { executeParsedCommand, parseCommand } from "./commanding";
import { HudOverlay } from "./HudOverlay";
import { AlertToasts } from "./AlertToasts";
import { useNotificationStore } from "../../store/notificationStore";
import { useKeyboardShortcuts } from "../../hooks/useKeyboardShortcuts";
import { ShortcutOverlay } from "../common/ShortcutOverlay";
import { WORKSPACE_PRESET_STORAGE_KEY } from "../../workspace/presets";
import { GlobalHeader } from "./GlobalHeader";
import { PrimarySidebar } from "./PrimarySidebar";
import { WorkspaceOverflowMenu } from "./WorkspaceOverflowMenu";

export type WorkspacePreset = "trader" | "quant" | "pm" | "risk" | "ops";

type TerminalShellContextValue = {
  preset: WorkspacePreset;
  setPreset: (preset: WorkspacePreset) => void;
  rightRailOpen: boolean;
  setRightRailOpen: (open: boolean) => void;
  toggleRightRail: () => void;
};

const TerminalShellContext = createContext<TerminalShellContextValue | null>(null);

type RightRailSection = {
  id: string;
  title: string;
  content: ReactNode;
};

type Props = {
  children: ReactNode;
  contentClassName?: string;
  hideTickerLoader?: boolean;
  statusBarTickerOverride?: string;
  showMobileBottomNav?: boolean;
  workspacePresetStorageKey?: string;
  defaultPreset?: WorkspacePreset;
  showWorkspaceControls?: boolean;
  rightRailTitle?: string;
  rightRailSections?: RightRailSection[];
  rightRailContent?: ReactNode;
  defaultRightRailOpen?: boolean;
  rightRailStorageKey?: string;
};

function usePersistedState<T>(storageKey: string | undefined, fallback: T): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => {
    if (!storageKey) return fallback;
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return fallback;
      return JSON.parse(raw) as T;
    } catch {
      return fallback;
    }
  });

  useEffect(() => {
    if (!storageKey) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify(value));
    } catch {
      // ignore storage failures
    }
  }, [storageKey, value]);

  return [value, setValue];
}

function DefaultRightRail({ title, sections }: { title: string; sections: RightRailSection[] }) {
  return (
    <aside className="hidden xl:flex h-full w-72 shrink-0 flex-col border-l border-terminal-border bg-terminal-panel">
      <div className="border-b border-terminal-border px-3 py-2">
        <div className="ot-type-panel-title text-terminal-accent">{title}</div>
        <div className="ot-type-panel-subtitle text-terminal-muted">Contextual tools and quick actions</div>
      </div>
      <div className="flex-1 space-y-2 overflow-auto p-2">
        {sections.map((section) => (
          <section key={section.id} className="rounded-sm border border-terminal-border bg-terminal-bg/40">
            <header className="border-b border-terminal-border px-2 py-1">
              <div className="ot-type-panel-title text-terminal-muted">{section.title}</div>
            </header>
            <div className="p-2 text-xs text-terminal-text">{section.content}</div>
          </section>
        ))}
      </div>
    </aside>
  );
}

export function TerminalShell({
  children,
  contentClassName = "",
  hideTickerLoader: _hideTickerLoader = false,
  statusBarTickerOverride: _statusBarTickerOverride,
  showMobileBottomNav: _showMobileBottomNav = false,
  workspacePresetStorageKey,
  defaultPreset = "trader",
  showWorkspaceControls: _showWorkspaceControls = true,
  rightRailTitle = "Context Rail",
  rightRailSections,
  rightRailContent,
  defaultRightRailOpen = false,
  rightRailStorageKey,
}: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const [preset, setPreset] = usePersistedState<WorkspacePreset>(
    workspacePresetStorageKey ?? WORKSPACE_PRESET_STORAGE_KEY,
    defaultPreset,
  );
  const [rightRailOpen, setRightRailOpen] = usePersistedState<boolean>(
    rightRailStorageKey,
    defaultRightRailOpen,
  );
  const fetchUnreadCount = useNotificationStore((s) => s.fetchUnreadCount);

  useKeyboardShortcuts();

  const hasRightRail = Boolean(rightRailContent) || Boolean(rightRailSections?.length);

  const shellCtx = useMemo<TerminalShellContextValue>(
    () => ({
      preset,
      setPreset,
      rightRailOpen,
      setRightRailOpen,
      toggleRightRail: () => setRightRailOpen(!rightRailOpen),
    }),
    [preset, setPreset, rightRailOpen, setRightRailOpen],
  );

  useEffect(() => {
    void fetchUnreadCount();
    const timer = window.setInterval(() => {
      void fetchUnreadCount();
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [fetchUnreadCount]);

  return (
    <TerminalShellContext.Provider value={shellCtx}>
      <div className="flex h-screen w-full overflow-hidden bg-terminal-bg text-terminal-text">
        <PrimarySidebar />

        <div className="relative z-10 flex min-w-0 flex-1 flex-col">
          <GlobalHeader
            onExecute={async (command) => {
              const parsed = parseCommand(command);
              return executeParsedCommand(parsed, navigate);
            }}
          />
          <div className="min-h-0 flex flex-1 overflow-hidden">
            <ErrorBoundary>
              <div className={`relative z-0 min-h-0 min-w-0 flex-1 overflow-auto ${contentClassName}`.trim()}>
                {children}
              </div>
            </ErrorBoundary>
            {hasRightRail && rightRailOpen
              ? rightRailContent ?? (
                  <DefaultRightRail title={rightRailTitle} sections={rightRailSections ?? []} />
                )
              : null}
          </div>
        </div>

        <div className="md:hidden"><MobileBottomNav /></div>
        <WorkspaceOverflowMenu
          preset={preset}
          setPreset={setPreset}
          hasRightRail={hasRightRail}
          rightRailOpen={rightRailOpen}
          toggleRightRail={() => setRightRailOpen(!rightRailOpen)}
        />
        <CommandPalette />
        <HudOverlay />
        <AlertToasts />
        <ShortcutOverlay />
      </div>
    </TerminalShellContext.Provider>
  );
}

export function useTerminalShellWorkspace() {
  const ctx = useContext(TerminalShellContext);
  if (!ctx) {
    throw new Error("useTerminalShellWorkspace must be used within TerminalShell");
  }
  return ctx;
}
