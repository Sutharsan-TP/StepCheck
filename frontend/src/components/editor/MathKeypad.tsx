"use client";

import { useState } from "react";

import { TabPanel, Tabs } from "@/components/ui/tabs";
import { KEYPAD, type Key, type KeypadPage } from "@/lib/keypad";
import { cn } from "@/lib/utils";

const PAGES: { value: KeypadPage; label: string }[] = [
  { value: "basic", label: "Basic" },
  { value: "functions", label: "Functions" },
  { value: "calculus", label: "Calculus" },
];

/**
 * A calculator-style keypad. Keys never take focus (mousedown is prevented), so the
 * step being edited keeps its caret and selection while keys are pressed.
 */
export function MathKeypad({ onKey, target }: { onKey: (key: Key) => void; target: string }) {
  const [page, setPage] = useState<KeypadPage>("basic");
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted-surface p-2" aria-label="Maths keypad">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tabs<KeypadPage> idPrefix="keypad" label="Keypad pages" value={page} onChange={setPage} items={PAGES} />
        <span className="px-1 text-xs text-muted" aria-live="polite">
          Typing into: {target}
        </span>
      </div>
      <TabPanel idPrefix="keypad" value={page}>
        <div className="grid grid-cols-6 gap-1.5">
          {KEYPAD[page].map((key, index) => (
            <button
              key={`${page}-${index}`}
              type="button"
              aria-label={key.aria}
              title={key.insert ? `Inserts ${key.insert.replace("|", "…")}` : key.aria}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => onKey(key)}
              className={cn(
                "h-10 min-w-0 rounded-md border px-1 text-sm font-medium transition-colors",
                "focus-visible:outline-2 focus-visible:outline-primary",
                key.tone === "operator" && "border-primary/30 bg-primary-soft text-foreground hover:border-primary/60",
                key.tone === "action" && "border-border bg-background text-muted-strong hover:text-foreground",
                !key.tone && "border-border bg-card text-foreground hover:border-primary/50",
              )}
            >
              {key.label}
            </button>
          ))}
        </div>
      </TabPanel>
    </div>
  );
}
