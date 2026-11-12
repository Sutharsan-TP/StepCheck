"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { describeError, transcribe, verify } from "@/lib/api";
import { clearSession, saveSession } from "@/lib/session";
import type { TranscriptionResponse } from "@/lib/types";

/** Workspace actions: transcribe an image and verify confirmed steps (then open /results). */
export function useStepCheck() {
  const router = useRouter();
  const [verifying, setVerifying] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function verifySteps(steps: string[], imagePreview: string | null = null): Promise<void> {
    if (verifying) return;
    setVerifying(true);
    setError(null);
    try {
      const verification = await verify(steps);
      saveSession({ steps, verification, imagePreview });
      router.push("/results");
    } catch (e) {
      setError(describeError(e));
      setVerifying(false);
    }
  }

  async function transcribeImage(file: File): Promise<TranscriptionResponse | null> {
    if (transcribing) return null;
    setTranscribing(true);
    setError(null);
    try {
      return await transcribe(file);
    } catch (e) {
      setError(describeError(e));
      return null;
    } finally {
      setTranscribing(false);
    }
  }

  function startOver() {
    clearSession();
    router.push("/workspace");
  }

  return { verifySteps, transcribeImage, startOver, verifying, transcribing, error, clearError: () => setError(null) };
}
