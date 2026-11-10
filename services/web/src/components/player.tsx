"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";

export function MomentPlayer({
  src,
  start,
  end,
  label,
}: {
  src: string;
  start: number;
  end: number;
  label: string;
}) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const seek = () => {
      element.currentTime = start;
      void element.play().catch(() => undefined);
    };
    if (element.readyState >= 1) {
      seek();
    } else {
      element.addEventListener("loadedmetadata", seek, { once: true });
    }
  }, [src, start]);

  return (
    <div className="flex flex-col gap-2">
      <video
        ref={ref}
        src={`${src}#t=${start},${end}`}
        controls
        preload="metadata"
        className="aspect-video w-full rounded-lg bg-foreground"
      />
      <div className="flex items-center justify-between gap-3">
        <p className="font-mono text-xs text-muted-foreground">{label}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const element = ref.current;
            if (!element) return;
            element.currentTime = start;
            void element.play().catch(() => undefined);
          }}
        >
          Play from {formatClock(start)}
        </Button>
      </div>
    </div>
  );
}

function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}
