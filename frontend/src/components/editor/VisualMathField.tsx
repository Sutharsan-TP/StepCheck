"use client";

import type { MathfieldElement } from "mathlive";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Keys for the calculus operators. "#?" is an empty box to fill in, "#@" the current
 * selection. Every key inserts LaTeX that lib/latex-to-text.ts knows how to read.
 */
const CALCULUS_LAYOUT = {
  label: "Calculus",
  tooltip: "Derivatives, integrals and limits",
  rows: [
    [
      { label: "d/dx", tooltip: "Derivative", insert: "\\frac{d}{dx}\\left(#?\\right)" },
      { label: "∫ dx", tooltip: "Indefinite integral", insert: "\\int #?\\,dx" },
      { label: "∫ₐᵇ dx", tooltip: "Definite integral", insert: "\\int_{#?}^{#?}#?\\,dx" },
      { label: "lim", tooltip: "Limit", insert: "\\lim_{x\\to #?}#?" },
      { label: "[F]ₐᵇ", tooltip: "Evaluate between limits", insert: "\\left[#?\\right]_{#?}^{#?}" },
      { label: "+ C", tooltip: "Constant of integration", insert: "+C" },
    ],
    [
      { latex: "\\sin", tooltip: "Sine", insert: "\\sin\\left(#?\\right)" },
      { latex: "\\cos", tooltip: "Cosine", insert: "\\cos\\left(#?\\right)" },
      { latex: "\\tan", tooltip: "Tangent", insert: "\\tan\\left(#?\\right)" },
      { latex: "\\ln", tooltip: "Natural logarithm", insert: "\\ln\\left(#?\\right)" },
      { latex: "e^{x}", tooltip: "e to a power", insert: "e^{#?}" },
      { latex: "|x|", tooltip: "Absolute value", insert: "\\left|#?\\right|" },
    ],
    [
      { latex: "x^{2}", tooltip: "Squared", insert: "#@^{2}" },
      { latex: "x^{n}", tooltip: "Power", insert: "#@^{#?}" },
      { latex: "\\sqrt{x}", tooltip: "Square root", insert: "\\sqrt{#?}" },
      { latex: "\\frac{a}{b}", tooltip: "Fraction", insert: "\\frac{#@}{#?}" },
      { latex: "\\pi", tooltip: "Pi", insert: "\\pi" },
      { latex: "\\infty", tooltip: "Infinity", insert: "\\infty" },
    ],
  ],
};

let configured = false;

async function loadMathLive() {
  const { MathfieldElement } = await import("mathlive");
  if (!configured) {
    configured = true;
    // Fonts come from the KaTeX stylesheet the app already loads; MathLive uses the same families.
    MathfieldElement.fontsDirectory = null;
    MathfieldElement.soundsDirectory = null;
    window.mathVirtualKeyboard.layouts = ["numeric", CALCULUS_LAYOUT, "alphabetic"];
  }
  return MathfieldElement;
}

/**
 * A visual maths editor. The field keeps its own content (uncontrolled), starts from
 * `initialLatex`, and reports every edit as LaTeX through `onLatex`.
 */
export function VisualMathField({
  initialLatex,
  onLatex,
  label,
  invalid,
  onFocus,
}: {
  initialLatex: string;
  onLatex: (latex: string) => void;
  label: string;
  invalid?: boolean;
  onFocus?: () => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  // Latest props for the long-lived element listeners, without re-creating the element.
  const callbacks = useRef({ onLatex, onFocus });
  const initial = useRef(initialLatex);
  useEffect(() => {
    callbacks.current = { onLatex, onFocus };
  });

  useEffect(() => {
    let disposed = false;
    let field: MathfieldElement | null = null;
    loadMathLive()
      .then((MathfieldElement) => {
        if (disposed || !container.current) return;
        field = new MathfieldElement();
        field.mathVirtualKeyboardPolicy = "auto";
        field.setAttribute("aria-label", label);
        field.value = initial.current;
        field.addEventListener("input", () => callbacks.current.onLatex(field!.value));
        field.addEventListener("focusin", () => callbacks.current.onFocus?.());
        container.current.appendChild(field);
        setState("ready");
      })
      .catch(() => {
        if (!disposed) setState("failed");
      });
    return () => {
      disposed = true;
      field?.remove();
    };
    // The element is created once per mount; the label is read at that moment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col gap-1">
      <div
        ref={container}
        data-testid="visual-field"
        data-state={state}
        className={cn("visual-math-field", invalid && "visual-math-field-invalid")}
      />
      {state === "loading" && <span className="text-xs text-muted">Loading the visual editor…</span>}
      {state === "failed" && (
        <span role="alert" className="text-xs text-invalid">
          The visual editor couldn&apos;t load. Switch to the keypad to keep working.
        </span>
      )}
    </div>
  );
}
