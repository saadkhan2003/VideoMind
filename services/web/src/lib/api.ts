export type Video = {
  id: string;
  title: string;
  filename: string;
  duration_s: number | null;
  status: string;
  language: string | null;
  license: string;
};

export type Stage = {
  status: string;
  detail?: string;
  started_at?: string;
  finished_at?: string;
};

export type Job = {
  id: string;
  video_id: string;
  status: string;
  stage: string;
  progress: number;
  stages: Record<string, Stage>;
  error: string;
  attempts: number;
};

export type Hit = {
  segment_id: string;
  video_id: string;
  title: string;
  start_s: number;
  end_s: number;
  timestamp: string;
  end_timestamp: string;
  score: number;
  snippet: string;
  transcript_text: string;
  visual_caption: string;
  ocr_text: string;
  thumbnail_url: string;
  lang: string;
};

const API = "/backend";

async function readError(response: Response): Promise<string> {
  const text = await response.text();
  try {
    const body = JSON.parse(text) as { detail?: string };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* plain text */
  }
  return text || `Request failed (${response.status})`;
}

export async function searchMoments(query: string, videoId?: string): Promise<{
  took_ms: number;
  hits: Hit[];
}> {
  const params = new URLSearchParams({ q: query, k: "8" });
  if (videoId) params.set("video_id", videoId);
  const response = await fetch(`${API}/search?${params.toString()}`);
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function listVideos(): Promise<Video[]> {
  const response = await fetch(`${API}/videos`);
  if (!response.ok) throw new Error(await readError(response));
  const body = (await response.json()) as { videos: Video[] };
  return body.videos;
}

export async function uploadVideo(file: File, title: string): Promise<{ video_id: string; job: Job }> {
  const form = new FormData();
  form.set("file", file);
  if (title.trim()) form.set("title", title.trim());
  const response = await fetch(`${API}/videos`, { method: "POST", body: form });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function getJob(id: string): Promise<Job> {
  const response = await fetch(`${API}/jobs/${id}`);
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export function mediaUrl(videoId: string): string {
  return `${API}/videos/${videoId}/media`;
}

export function thumbnailUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${API}${path}`;
}
