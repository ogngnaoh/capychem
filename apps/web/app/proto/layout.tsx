"use client";

// HI-FI PROTOTYPE shell — persistent console-with-a-home (Overview · Workbench ·
// Runs · Compare), on-token. Launcher is the front door reached via "Start a run",
// so it is not a top-level nav item. Dark-mode toggle wired here (the full .dark
// palette lives in globals.css; we only flip the class on <html>).

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ProtoRibbon } from "./_ui";

const NAV = [
  { href: "/proto/overview", label: "Overview" },
  { href: "/proto/workbench", label: "Workbench" },
  { href: "/proto/runs", label: "Runs" },
  { href: "/proto/compare", label: "Compare" },
];

function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    // Sync from client-only localStorage on mount (SSR can't read it in a lazy
    // initializer). Matches the LiveRun.tsx convention for this pattern.
    const stored = localStorage.getItem("proto-theme");
    const isDark = stored === "dark";
    document.documentElement.classList.toggle("dark", isDark);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDark(isDark);
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("proto-theme", next ? "dark" : "light");
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

export default function ProtoLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <ProtoRibbon />
      <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-8 px-6">
          <Link
            href="/proto/overview"
            className="font-heading text-lg font-normal tracking-tight"
          >
            CapyChem
          </Link>
          <nav className="flex items-center gap-0.5" aria-label="Primary">
            {NAV.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "relative rounded-md px-3 py-1.5 text-sm transition-colors",
                    active
                      ? "font-medium text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  ].join(" ")}
                >
                  {item.label}
                  {active && (
                    <span className="absolute inset-x-3 -bottom-[13px] h-px bg-primary" />
                  )}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-xs text-muted-foreground md:inline">
              in-silico benchmark demonstrator
            </span>
            <ThemeToggle />
            <Link
              href="/proto/launcher"
              className="rounded-lg bg-primary px-3.5 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              Start a run
            </Link>
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-6 py-10">{children}</div>
    </div>
  );
}
