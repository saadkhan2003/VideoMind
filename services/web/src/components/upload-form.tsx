"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { UploadIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { uploadVideo } from "@/lib/api";

export function UploadForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Choose an mp4, mov, mkv, or webm file.");
      return;
    }
    setPending(true);
    setError("");
    try {
      const result = await uploadVideo(file, title);
      router.push(`/jobs/${result.job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="title">Title</FieldLabel>
          <Input
            id="title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Lecture 4 — backpropagation"
          />
          <FieldDescription>Shown on search results. The filename is used if you leave this blank.</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="file">Video file</FieldLabel>
          <Input
            id="file"
            type="file"
            accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.mkv,.webm"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <FieldDescription>Speech is transcribed, scene changes become keyframes, and both are indexed.</FieldDescription>
        </Field>
      </FieldGroup>
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Upload rejected</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div>
        <Button type="submit" disabled={pending}>
          {pending ? <Spinner data-icon="inline-start" /> : <UploadIcon data-icon="inline-start" />}
          {pending ? "Indexing" : "Start ingestion"}
        </Button>
      </div>
    </form>
  );
}
