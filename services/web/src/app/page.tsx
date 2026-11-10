import { SearchConsole } from "@/components/search-console";

export default function HomePage() {
  return (
    <div className="flex flex-col gap-8">
      <div className="flex max-w-2xl flex-col gap-3">
        <p className="text-sm font-medium text-primary">Multimodal video search</p>
        <h1 className="font-heading text-4xl leading-tight tracking-tight md:text-5xl">
          Find the second, not the file.
        </h1>
        <p className="text-base leading-7 text-muted-foreground">
          Ask where a lecture explains an idea, or when a diagram appears. VideoMind searches the
          transcript and the text on screen, then starts playback at that moment.
        </p>
      </div>
      <SearchConsole />
    </div>
  );
}
