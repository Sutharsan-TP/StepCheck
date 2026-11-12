"use client";

import { ImageUp } from "lucide-react";
import { useRef, useState } from "react";

import { ACCEPTED_IMAGE_TYPES, cn, MAX_IMAGE_BYTES } from "@/lib/utils";

export function validateImage(file: File): string | null {
  if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) return "Please choose a JPEG, PNG or WebP image.";
  if (file.size > MAX_IMAGE_BYTES) return "That image is larger than 5 MB. Try a smaller photo.";
  if (file.size === 0) return "That file is empty.";
  return null;
}

export function ImageDropzone({ onFile, disabled }: { onFile: (file: File) => void; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function accept(file: File | undefined) {
    if (!file) return;
    const problem = validateImage(file);
    setError(problem);
    if (!problem) onFile(file);
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-label="Upload a photo of handwritten work"
        onClick={() => !disabled && input.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            input.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled) accept(e.dataTransfer.files[0]);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors",
          "focus-visible:outline-2 focus-visible:outline-primary",
          dragging ? "border-primary bg-primary-soft" : "border-border bg-card hover:border-primary/50",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        <ImageUp className="size-8 text-primary" aria-hidden />
        <div>
          <p className="font-medium text-foreground">Drop a photo of your working here</p>
          <p className="text-sm text-muted">or click to choose a file · JPEG, PNG or WebP · up to 5 MB</p>
        </div>
      </div>
      <input
        ref={input}
        type="file"
        accept={ACCEPTED_IMAGE_TYPES.join(",")}
        className="sr-only"
        data-testid="image-input"
        tabIndex={-1}
        onChange={(e) => {
          accept(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      {error && (
        <p role="alert" className="text-sm text-invalid">
          {error}
        </p>
      )}
    </div>
  );
}
