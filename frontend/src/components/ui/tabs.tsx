"use client";

import type { KeyboardEvent, ReactNode } from "react";

import { cn } from "@/lib/utils";

export type TabItem<T extends string> = { value: T; label: ReactNode; icon?: ReactNode };

/** Accessible tab list (arrow-key navigation, aria-selected). Panels are rendered by the caller. */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  idPrefix,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  idPrefix: string;
}) {
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const index = items.findIndex((item) => item.value === value);
    const next = items[(index + (event.key === "ArrowRight" ? 1 : items.length - 1)) % items.length];
    onChange(next.value);
    document.getElementById(`${idPrefix}-tab-${next.value}`)?.focus();
  }

  return (
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="inline-flex rounded-lg border border-border bg-muted-surface p-1">
      {items.map((item) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            id={`${idPrefix}-tab-${item.value}`}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${item.value}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.value)}
            className={cn(
              "inline-flex items-center gap-2 rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
              "focus-visible:outline-2 focus-visible:outline-primary",
              selected ? "bg-card text-foreground shadow-sm" : "text-muted hover:text-foreground",
            )}
          >
            {item.icon}
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({ idPrefix, value, children }: { idPrefix: string; value: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`${idPrefix}-panel-${value}`} aria-labelledby={`${idPrefix}-tab-${value}`}>
      {children}
    </div>
  );
}
