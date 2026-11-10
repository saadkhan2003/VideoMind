import Link from "next/link";

import { Button } from "@/components/ui/button";

export function SiteHeader() {
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-4">
        <Link href="/" className="flex flex-col">
          <span className="font-heading text-lg leading-none tracking-tight">VideoMind</span>
          <span className="text-xs text-muted-foreground">Moments, not files</span>
        </Link>
        <nav className="flex items-center gap-2">
          <Button variant="ghost" render={<Link href="/" />}>
            Search
          </Button>
          <Button render={<Link href="/upload" />}>Upload</Button>
        </nav>
      </div>
    </header>
  );
}
