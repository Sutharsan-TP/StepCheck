import { useSyncExternalStore } from "react";

import type { VerifyResponse } from "./types";

/** The work currently being checked; kept in sessionStorage between pages. */
export type Session = {
  steps: string[];
  verification: VerifyResponse | null;
  imagePreview?: string | null;
};

const KEY = "stepcheck.session.v1";
const listeners = new Set<() => void>();
let cachedRaw: string | null = null;
let cached: Session | null = null;

function readRaw(): string | null {
  try {
    return window.sessionStorage.getItem(KEY);
  } catch {
    return null; // storage blocked (e.g. some private modes)
  }
}

function getSnapshot(): Session | null {
  const raw = readRaw();
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    try {
      const parsed = raw ? (JSON.parse(raw) as Session) : null;
      cached = parsed && Array.isArray(parsed.steps) ? parsed : null;
    } catch {
      cached = null;
    }
  }
  return cached;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function saveSession(session: Session): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    // Too large (e.g. image preview) or blocked: retry without the image, then give up quietly.
    try {
      window.sessionStorage.setItem(KEY, JSON.stringify({ ...session, imagePreview: null }));
    } catch {
      // the current page still works; only refresh persistence is lost
    }
  }
  notify();
}

export function clearSession(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
  notify();
}

/** Current session; null during server rendering and when nothing is stored. */
export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}

const noopSubscribe = () => () => {};

/** False during server rendering / hydration, true once running in the browser. */
export function useHydrated(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}
