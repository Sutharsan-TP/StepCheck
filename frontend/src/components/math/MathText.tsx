import { renderLatex } from "@/lib/math-renderer";
import { cn } from "@/lib/utils";

/** Renders LaTeX with KaTeX (trust disabled). `label` is the plain-text form for screen readers. */
export function MathText({
  latex,
  label,
  display = false,
  className,
}: {
  latex: string;
  label?: string;
  display?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn("math", display && "block overflow-x-auto py-1", className)}
      aria-label={label}
      role={label ? "math" : undefined}
      // KaTeX escapes text and, with trust disabled, emits no links, scripts or styles from input.
      dangerouslySetInnerHTML={{ __html: renderLatex(latex, display) }}
    />
  );
}
