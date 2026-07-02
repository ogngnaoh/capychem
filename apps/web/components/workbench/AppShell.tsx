"use client";

// Persistent console-with-a-home shell (Overview · Workbench · Runs · Compare),
// on-token. The launcher is the front door reached via "Start a run", so it is not a
// top-level nav item. Dark-mode toggle flips `.dark` on <html> (the full palette lives
// in globals.css) and persists to localStorage under `theme`; the no-flash script in
// app/layout.tsx applies it before first paint. "Workbench" points at the most-recent
// run (or /runs when there are none).

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { listRuns } from "@/lib/api";

function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    // The no-flash script already set the class; sync React state to it on mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      /* ignore (private mode / disabled storage) */
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={dark}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="inline-flex size-8 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      {dark ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [workbenchHref, setWorkbenchHref] = useState("/runs");

  useEffect(() => {
    let closed = false;
    listRuns({ sort: "started_at", order: "desc" })
      .then((runs) => {
        if (!closed && runs.length > 0) setWorkbenchHref(`/runs/${runs[0].run_id}`);
      })
      .catch(() => {
        /* fall back to /runs */
      });
    return () => {
      closed = true;
    };
  }, []);

  const isRunDetail = /^\/runs\/\d+/.test(pathname);
  const nav = [
    { href: "/", label: "Overview", active: pathname === "/" },
    { href: workbenchHref, label: "Workbench", active: isRunDetail },
    { href: "/runs", label: "Runs", active: pathname === "/runs" },
    { href: "/compare", label: "Compare", active: pathname.startsWith("/compare") },
  ];

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-8 px-6">
          <Link href="/" className="font-heading text-lg font-normal tracking-tight">
            CapyChem
          </Link>
          <nav className="flex items-center gap-0.5" aria-label="Primary">
            {nav.map((item) => (
              <Link
                key={item.label}
                href={item.href}
                aria-current={item.active ? "page" : undefined}
                className={[
                  "relative rounded-md px-3 py-1.5 text-sm transition-colors",
                  item.active
                    ? "font-medium text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                ].join(" ")}
              >
                {item.label}
                {item.active && (
                  <span className="absolute inset-x-3 -bottom-[13px] h-px bg-primary" />
                )}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-xs text-muted-foreground md:inline">
              in-silico benchmark demonstrator
            </span>
            <ThemeToggle />
            <Link
              href="/launch"
              className="rounded-lg bg-primary px-3.5 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              Start a run
            </Link>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">{children}</main>
    </div>
  );
}
