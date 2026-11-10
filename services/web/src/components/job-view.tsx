"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress";
import { getJob, Job } from "@/lib/api";

const ORDER = ["extract_audio", "asr", "scenes", "captions", "chunk", "embed", "upsert"];

export function JobView({ id }: { id: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const next = await getJob(id);
        if (stop) return;
        setJob(next);
        if (next.status === "queued" || next.status === "processing") {
          window.setTimeout(tick, 1500);
        }
      } catch (err) {
        if (!stop) setError(err instanceof Error ? err.message : "Could not load the job");
      }
    }
    void tick();
    return () => {
      stop = true;
    };
  }, [id]);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Job unavailable</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }
  if (!job) {
    return <p className="text-sm text-muted-foreground">Loading job…</p>;
  }
  const percent = Math.round((job.progress || 0) * 100);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Job {job.id.slice(0, 8)}
          <Badge variant={job.status === "failed" ? "destructive" : "secondary"}>{job.status}</Badge>
        </CardTitle>
        <CardDescription>Video {job.video_id}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Progress value={percent}>
          <ProgressLabel>Progress</ProgressLabel>
          <ProgressValue />
        </Progress>
        <ol className="flex flex-col gap-2">
          {ORDER.map((name) => {
            const stage = job.stages[name];
            return (
              <li key={name} className="flex items-center justify-between gap-3 text-sm">
                <span className="font-mono">{name}</span>
                <span className="text-muted-foreground">{stage?.status ?? "waiting"}</span>
              </li>
            );
          })}
        </ol>
        {job.error ? (
          <Alert variant="destructive">
            <AlertTitle>The job failed</AlertTitle>
            <AlertDescription>{job.error}</AlertDescription>
          </Alert>
        ) : null}
        {job.status === "indexed" ? (
          <div>
            <Button render={<Link href={`/?q=`} />}>Search this library</Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
