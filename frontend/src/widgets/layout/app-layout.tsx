import { ViewTransition } from "react";

import { Sidebar } from "./sidebar";

export function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh overflow-hidden bg-[var(--ege-canvas)] text-[var(--ege-text)] p-1 md:pb-2.5 md:pr-2.5 md:pt-2 md:pl-0">
      <Sidebar />
      <main className="flex flex-1 overflow-hidden">
        <ViewTransition>{children}</ViewTransition>
      </main>
    </div>
  );
}
