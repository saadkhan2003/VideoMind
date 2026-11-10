"use client";

import { FormEvent, useEffect, useState } from "react";
import { SearchIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { MomentPlayer } from "@/components/player";
import { Hit, listVideos, mediaUrl, searchMoments, thumbnailUrl, Video } from "@/lib/api";

export function SearchConsole() {
  const [query, setQuery] = useState("");
  const [videoId, setVideoId] = useState("");
  const [videos, setVideos] = useState<Video[]>([]);
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [took, setTook] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [active, setActive] = useState<Hit | null>(null);

  useEffect(() => {
    listVideos()
      .then(setVideos)
      .catch(() => setVideos([]));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (!text) return;
    setLoading(true);
    setError("");
    setActive(null);
    try {
      const result = await searchMoments(text, videoId || undefined);
      setHits(result.hits);
      setTook(result.took_ms);
    } catch (err) {
      setHits(null);
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={onSubmit} className="flex flex-col gap-3 md:flex-row">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Where does the lecturer explain backpropagation?"
          aria-label="Search query"
          className="h-10 md:flex-1"
        />
        <select
          value={videoId}
          onChange={(event) => setVideoId(event.target.value)}
          aria-label="Limit to one video"
          className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All indexed videos</option>
          {videos.map((video) => (
            <option key={video.id} value={video.id}>
              {video.title}
            </option>
          ))}
        </select>
        <Button type="submit" disabled={loading || !query.trim()} size="lg">
          <SearchIcon data-icon="inline-start" />
          Search
        </Button>
      </form>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Search did not run</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {loading ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : null}

      {!loading && hits && hits.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>No moment matched</EmptyTitle>
            <EmptyDescription>
              Try a phrase from the soundtrack, or a title you remember from a slide.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {!loading && hits && hits.length > 0 ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            {hits.length} moment{hits.length === 1 ? "" : "s"} · {took?.toFixed(0)} ms
          </p>
          {hits.map((hit) => (
            <Card key={hit.segment_id}>
              <CardHeader>
                <CardTitle>{hit.title}</CardTitle>
                <CardDescription className="font-mono text-primary">
                  {hit.timestamp}–{hit.end_timestamp}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex flex-col gap-4 md:flex-row">
                  {hit.thumbnail_url ? (
                    // Keyframes are generated JPEGs served by the API, not remote optimized assets.
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={thumbnailUrl(hit.thumbnail_url)}
                      alt=""
                      className="aspect-video w-full rounded-lg object-cover md:w-48"
                    />
                  ) : null}
                  <div className="flex min-w-0 flex-1 flex-col gap-2">
                    <p className="text-sm leading-6">{hit.snippet}</p>
                    <div className="flex flex-wrap gap-2">
                      {hit.visual_caption ? <Badge variant="secondary">On screen</Badge> : null}
                      {hit.ocr_text ? <Badge variant="outline">Visible text</Badge> : null}
                      {hit.lang ? <Badge variant="outline">{hit.lang}</Badge> : null}
                    </div>
                    <div>
                      <Button
                        variant={active?.segment_id === hit.segment_id ? "secondary" : "outline"}
                        onClick={() => setActive(hit)}
                      >
                        Play this moment
                      </Button>
                    </div>
                  </div>
                </div>
                {active?.segment_id === hit.segment_id ? (
                  <MomentPlayer
                    src={mediaUrl(hit.video_id)}
                    start={hit.start_s}
                    end={hit.end_s}
                    label={`${hit.title} · ${hit.timestamp}`}
                  />
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
