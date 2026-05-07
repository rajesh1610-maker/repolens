"use client";

import { useEffect } from "react";

type HotkeyMap = Record<string, (event: KeyboardEvent) => void>;

const TYPING_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (TYPING_TAGS.has(target.tagName)) return true;
  if (target.isContentEditable) return true;
  return false;
}

/**
 * Window-level keydown listener with one handler per key.
 * Skips when the user is typing in an input/textarea/contenteditable.
 *
 * Use lowercase keys ("j", "k", "o"). The handler receives the raw event
 * so it can preventDefault() if needed.
 */
export function useHotkeys(map: HotkeyMap, deps: ReadonlyArray<unknown> = []): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTyping(e.target)) return;
      const handler = map[e.key.toLowerCase()];
      if (handler) handler(e);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
