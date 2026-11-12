"use client";

import { Camera, Keyboard, Loader2 } from "lucide-react";
import { useState } from "react";

import { StepEditor } from "@/components/editor/StepEditor";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { ImageDropzone } from "@/components/upload/ImageDropzone";
import { TranscriptionReview } from "@/components/upload/TranscriptionReview";
import { useStepCheck } from "@/hooks/useStepCheck";
import { useHydrated, useSession } from "@/lib/session";
import type { TranscriptionResponse } from "@/lib/types";

type Mode = "typed" | "handwritten";

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export default function WorkspacePage() {
  const hydrated = useHydrated();
  const session = useSession();
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-serif text-3xl font-semibold">Check a solution</h1>
        <p className="text-muted-strong">
          Enter the problem on the first line, then each step of your working on its own line.
        </p>
      </div>
      {hydrated ? (
        <Workspace initialSteps={session?.steps} />
      ) : (
        <div className="h-64 animate-pulse rounded-lg bg-muted-surface" aria-hidden />
      )}
    </div>
  );
}

function Workspace({ initialSteps }: { initialSteps?: string[] }) {
  const [mode, setMode] = useState<Mode>("typed");
  const [transcription, setTranscription] = useState<TranscriptionResponse | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const { verifySteps, transcribeImage, verifying, transcribing, error } = useStepCheck();

  async function onFile(file: File) {
    setTranscription(null);
    setPreview(await readAsDataUrl(file).catch(() => null));
    const result = await transcribeImage(file);
    if (result) setTranscription(result);
  }

  return (
    <div className="flex flex-col gap-5">
      <Tabs<Mode>
        idPrefix="input"
        label="How do you want to enter your work?"
        value={mode}
        onChange={setMode}
        items={[
          { value: "typed", label: "Type steps", icon: <Keyboard className="size-4" aria-hidden /> },
          { value: "handwritten", label: "Upload photo", icon: <Camera className="size-4" aria-hidden /> },
        ]}
      />

      {error && (
        <Alert tone="error" title="Something went wrong">
          {error}
        </Alert>
      )}

      {mode === "typed" ? (
        <TabPanel idPrefix="input" value="typed">
          <StepEditor initialSteps={initialSteps} onSubmit={(steps) => verifySteps(steps)} submitting={verifying} />
        </TabPanel>
      ) : (
        <TabPanel idPrefix="input" value="handwritten">
          {transcription ? (
            <TranscriptionReview
              key={transcription.request_id}
              transcription={transcription}
              imageSrc={preview}
              submitting={verifying}
              onCancel={() => {
                setTranscription(null);
                setPreview(null);
              }}
              onConfirm={(steps) => verifySteps(steps, preview)}
            />
          ) : (
            <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
              <ImageDropzone onFile={onFile} disabled={transcribing} />
              <Card>
                <CardContent className="flex flex-col gap-3 py-5 text-sm text-muted-strong">
                  {transcribing ? (
                    <p className="flex items-center gap-2 font-medium text-foreground" role="status">
                      <Loader2 className="size-4 animate-spin" aria-hidden /> Reading your handwriting…
                    </p>
                  ) : (
                    <p className="font-medium text-foreground">Tips for a good photo</p>
                  )}
                  <ul className="list-disc space-y-1 pl-5">
                    <li>Write one step per line, top to bottom.</li>
                    <li>Use good light and keep the page flat.</li>
                    <li>You&apos;ll review every line before anything is checked.</li>
                  </ul>
                  {preview && transcribing && (
                    // eslint-disable-next-line @next/next/no-img-element -- local data URL preview
                    <img src={preview} alt="Uploaded handwritten working" className="mt-2 rounded-md border border-border" />
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </TabPanel>
      )}
    </div>
  );
}
