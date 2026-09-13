import { useState } from "react";

import { useSettingsStore, type ThemeVariant } from "../../store/settingsStore";
import { TerminalSelect } from "../terminal/TerminalSelect";
import type { WorkspacePreset } from "./TerminalShell";

const PRESETS: Array<{ id: WorkspacePreset; label: string }> = [
  { id: "trader", label: "Trader" },
  { id: "quant", label: "Quant" },
  { id: "pm", label: "PM" },
  { id: "risk", label: "Risk" },
  { id: "ops", label: "Ops" },
];

export function WorkspaceOverflowMenu({
  preset,
  setPreset,
  hasRightRail,
  rightRailOpen,
  toggleRightRail,
}: {
  preset: WorkspacePreset;
  setPreset: (preset: WorkspacePreset) => void;
  hasRightRail: boolean;
  rightRailOpen: boolean;
  toggleRightRail: () => void;
}) {
  const [open, setOpen] = useState(false);
  const themeVariant = useSettingsStore((state) => state.themeVariant);
  const setThemeVariant = useSettingsStore((state) => state.setThemeVariant);
  const hudOverlayEnabled = useSettingsStore((state) => state.hudOverlayEnabled);
  const setHudOverlayEnabled = useSettingsStore((state) => state.setHudOverlayEnabled);

  return (
    <div className="fixed bottom-4 right-4 z-50 hidden lg:block">
      {open ? (
        <div className="mb-2 w-64 rounded-lg border border-terminal-border bg-terminal-panel p-3 shadow-2xl" role="dialog" aria-label="Workspace options">
          <p className="mb-2 text-xs font-semibold text-terminal-text">Workspace options</p>
          <label className="block text-xs text-terminal-muted">
            Preset
            <TerminalSelect
              className="mt-1 w-full"
              value={preset}
              onChange={(event) => {
                const next = event.target.value as WorkspacePreset;
                setPreset(next);
                window.dispatchEvent(new CustomEvent("ot:preset-change", { detail: next }));
              }}
            >
              {PRESETS.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
            </TerminalSelect>
          </label>
          <label className="mt-3 block text-xs text-terminal-muted">
            Theme
            <TerminalSelect className="mt-1 w-full" value={themeVariant} onChange={(event) => setThemeVariant(event.target.value as ThemeVariant)}>
              <option value="terminal-noir">Terminal Noir</option>
              <option value="classic-bloomberg">Classic Bloomberg</option>
              <option value="light-desk">Light Desk</option>
              <option value="custom">Custom</option>
            </TerminalSelect>
          </label>
          <button type="button" className="mt-3 w-full rounded border border-terminal-border px-2 py-2 text-left text-xs text-terminal-muted hover:text-terminal-text" onClick={() => setHudOverlayEnabled(!hudOverlayEnabled)}>
            {hudOverlayEnabled ? "Hide diagnostic HUD" : "Show diagnostic HUD"}
          </button>
          {hasRightRail ? (
            <button type="button" className="mt-2 w-full rounded border border-terminal-border px-2 py-2 text-left text-xs text-terminal-muted hover:text-terminal-text" onClick={toggleRightRail}>
              {rightRailOpen ? "Hide context tools" : "Show context tools"}
            </button>
          ) : null}
        </div>
      ) : null}
      <button type="button" onClick={() => setOpen((value) => !value)} className="rounded-full border border-terminal-border bg-terminal-panel px-3 py-2 text-xs text-terminal-muted shadow-lg hover:border-terminal-accent/45 hover:text-terminal-text" aria-expanded={open}>
        Workspace
      </button>
    </div>
  );
}
