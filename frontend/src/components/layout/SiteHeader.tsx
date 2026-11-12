import { SquareCheckBig } from "lucide-react";
import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="border-b border-border bg-card/80 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-serif text-lg font-semibold text-foreground">
          <SquareCheckBig className="size-5 text-primary" aria-hidden />
          StepCheck
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          <Link href="/workspace" className="rounded-md px-3 py-1.5 text-muted-strong hover:bg-muted-surface hover:text-foreground">
            Check a solution
          </Link>
        </nav>
      </div>
    </header>
  );
}
