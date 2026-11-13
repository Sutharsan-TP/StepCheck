"use client";

import { useEffect } from "react";

import { wakeBackend } from "@/lib/api";

/** Wakes a sleeping backend as soon as any page loads; renders nothing. */
export function BackendWakeup() {
  useEffect(() => {
    wakeBackend();
  }, []);
  return null;
}
