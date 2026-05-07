"use client";

import { useEffect, useState } from "react";
import { Keyboard, X } from "lucide-react";

/**
 * Global hotkey reference overlay. Press `?` to toggle, Esc to close.
 *
 * Listens at the window level. Skips while the user is typing — same
 * rule the rest of the hotkey infrastructure uses, so `?` inside an
 * input/textarea is a literal `?` (which a keyboard-shortcut overlay
 * stealing it would feel broken).
 *
 * Lives in the layout so every page benefits without each one
 * re-registering.
 */
export function HotkeyOverlay() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      // Esc closes regardless of focus context — the overlay itself is
      // a modal-ish thing that should always dismiss.
      if (e.key === "Escape" && open) {
        setOpen(false);
        return;
      }

      // `?` toggles, but only when NOT typing in an input. Same focus
      // rule as useHotkeys.
      const target = e.target;
      const typing =
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);
      if (typing) return;

      if (e.key === "?") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-md rounded-lg border border-zinc-700 bg-zinc-950 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
          <div className="flex items-center gap-2">
            <Keyboard size={16} className="text-teal-400" />
            <h2 className="text-sm font-semibold">Keyboard shortcuts</h2>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="text-zinc-500 hover:text-zinc-200 transition-colors"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </header>

        <div className="p-5 space-y-5 text-xs">
          <Group title="Inbox">
            <Row keys={["j"]} desc="Move selection down" />
            <Row keys={["k"]} desc="Move selection up" />
            <Row keys={["o"]} desc="Open selected item on GitHub" />
          </Group>
          <Group title="Anywhere">
            <Row keys={["?"]} desc="Show this shortcuts panel" />
            <Row keys={["Esc"]} desc="Close this panel" />
          </Group>
        </div>
      </div>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-2">
        {title}
      </div>
      <ul className="space-y-1.5">{children}</ul>
    </div>
  );
}

function Row({ keys, desc }: { keys: string[]; desc: string }) {
  return (
    <li className="flex items-center justify-between gap-3">
      <span className="text-zinc-300">{desc}</span>
      <span className="flex gap-1 shrink-0">
        {keys.map((k) => (
          <kbd
            key={k}
            className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-[11px] text-zinc-200 font-mono"
          >
            {k}
          </kbd>
        ))}
      </span>
    </li>
  );
}
