import "katex/dist/katex.min.css";
import "./globals.css";

import type { Metadata } from "next";
import { Geist, Geist_Mono, Source_Serif_4 } from "next/font/google";

import { BackendWakeup } from "@/components/layout/BackendWakeup";
import { SiteHeader } from "@/components/layout/SiteHeader";

const sans = Geist({ variable: "--font-sans-face", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono-face", subsets: ["latin"] });
const serif = Source_Serif_4({ variable: "--font-serif-face", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "StepCheck",
  description: "Find the first mistake in a step-by-step algebra solution, understand why, and fix it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} ${serif.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <BackendWakeup />
        <SiteHeader />
        <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-8 sm:px-6">{children}</main>
        <footer className="border-t border-border py-6 text-center text-xs text-muted">
          StepCheck verifies every step with a deterministic symbolic engine. AI only reads handwriting and
          phrases explanations.
        </footer>
      </body>
    </html>
  );
}
