import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type Tone = "info" | "success" | "warning" | "error";

const tones: Record<Tone, { className: string; Icon: typeof Info }> = {
  info: { className: "border-primary/30 bg-primary-soft text-foreground", Icon: Info },
  success: { className: "border-valid/40 bg-valid-soft text-foreground", Icon: CheckCircle2 },
  warning: { className: "border-review/40 bg-review-soft text-foreground", Icon: AlertTriangle },
  error: { className: "border-invalid/40 bg-invalid-soft text-foreground", Icon: XCircle },
};

export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const { className: toneClass, Icon } = tones[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("flex gap-3 rounded-md border px-4 py-3 text-sm", toneClass, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="flex flex-col gap-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="text-muted-strong">{children}</div>}
      </div>
    </div>
  );
}
