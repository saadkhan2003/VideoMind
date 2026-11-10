import type { Metadata } from "next";
import { Fraunces, Geist, IBM_Plex_Mono } from "next/font/google";

import { SiteHeader } from "@/components/site-header";

import "./globals.css";

const sans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const display = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
});

const mono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "VideoMind",
  description: "Search a video and jump to the second that answers the question.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${display.variable} ${mono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <SiteHeader />
        <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-8">{children}</main>
        <footer className="border-t border-border">
          <p className="mx-auto w-full max-w-6xl px-4 py-4 text-xs text-muted-foreground">
            VideoMind is a portfolio project by Muhammad Saad Khan. Retrieval numbers in the README
            stay blank until a labeled eval is run.
          </p>
        </footer>
      </body>
    </html>
  );
}
