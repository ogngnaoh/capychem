"use client";

// LOW-FI PROTOTYPE shell — throwaway. Persistent app shell (console-with-a-home)
// showing the locked IA: Overview · Workbench · Runs · Compare. Launcher is the
// front door reached via "Start a run", so it is not a top-level nav item.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ProtoRibbon } from "./_ui";

const NAV = [
  { href: "/proto/overview", label: "Overview" },
  { href: "/proto/workbench", label: "Workbench" },
  { href: "/proto/runs", label: "Runs" },
  { href: "/proto/compare", label: "Compare" },
];

export default function ProtoLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen bg-background">
      <ProtoRibbon />
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-6">
          <Link href="/proto/overview" className="font-heading text-lg font-normal">
            CapyChem
          </Link>
          <nav className="flex items-center gap-1" aria-label="Primary">
            {NAV.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "rounded-md px-3 py-1.5 text-sm transition-colors",
                    active
                      ? "bg-muted font-medium text-foreground"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  ].join(" ")}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-xs text-muted-foreground sm:inline">
              in-silico benchmark demonstrator
            </span>
            <Link
              href="/proto/launcher"
              className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Start a run
            </Link>
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-6 py-8">{children}</div>
    </div>
  );
}
