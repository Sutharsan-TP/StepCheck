import { useSyncExternalStore } from "react";

/** How a student enters maths: typing into a text box with a keypad, or the visual editor. */
export type InputMode = "keypad" | "visual";

const KEY = "stepcheck.inputMode.v1";
const DEFAULT_MODE: InputMode = "keypad";
const listeners = new Set<() => void>();

export function readInputMode(): InputMode {
  try {
    const stored = window.localStorage.getItem(KEY);
    return stored === "visual" || stored === "keypad" ? stored : DEFAULT_MODE;
  } catch {
    return DEFAULT_MODE; // storage blocked or unavailable: the preference just isn't remembered
  }
}

export function saveInputMode(mode: InputMode): void {
  try {
    window.localStorage.setItem(KEY, mode);
  } catch {
    // keep working for this page view without persisting
  }
  memory = mode;
  listeners.forEach((listener) => listener());
}

// Last value chosen in this page view, so the toggle works even when storage is blocked.
let memory: InputMode | null = null;

function getSnapshot(): InputMode {
  return memory ?? readInputMode();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === KEY) {
      memory = null; // another tab changed it: read the stored value again
      listener();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** The remembered input mode and a setter. Server rendering uses the default. */
export function useInputMode(): [InputMode, (mode: InputMode) => void] {
  const mode = useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT_MODE);
  return [mode, saveInputMode];
}

/** Test helper: forget everything remembered in memory. */
export function resetInputModeMemory(): void {
  memory = null;
}
