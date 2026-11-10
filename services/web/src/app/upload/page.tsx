import { UploadForm } from "@/components/upload-form";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function UploadPage() {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="font-heading text-3xl tracking-tight">Index a video</h1>
        <p className="text-sm leading-6 text-muted-foreground">
          The job extracts audio, transcribes it with word timestamps, grabs a keyframe when the
          picture changes, captions those frames, and writes searchable segments.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>New video</CardTitle>
          <CardDescription>mp4, mov, mkv, or webm. Very long files are rejected.</CardDescription>
        </CardHeader>
        <CardContent>
          <UploadForm />
        </CardContent>
      </Card>
    </div>
  );
}
