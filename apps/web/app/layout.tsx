import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Observability Platform",
  description: "Trace, attribute, replay — for LLM agents in production.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-zinc-950 text-zinc-100 antialiased">
        <nav className="border-b border-zinc-800 px-6 py-3 flex items-center gap-6">
          <a href="/" className="font-semibold text-zinc-100">ai-obs</a>
          <a href="/runs" className="text-sm text-zinc-400 hover:text-zinc-100">Runs</a>
          <a href="/agents" className="text-sm text-zinc-400 hover:text-zinc-100">Agents</a>
          <a href="/tools" className="text-sm text-zinc-400 hover:text-zinc-100">Tools</a>
          <a href="/diff" className="text-sm text-zinc-400 hover:text-zinc-100">Diff</a>
        </nav>
        <main className="min-h-[calc(100vh-3rem)]">{children}</main>
      </body>
    </html>
  );
}
