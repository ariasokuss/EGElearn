import { ViewTransition } from "react";

import { Sidebar } from "./sidebar";

export function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh overflow-hidden bg-[var(--ege-canvas)] text-[var(--ege-text)] p-2 md:gap-2.5 md:p-3">
      <Sidebar />
      <main className="flex flex-1 overflow-hidden">
        <ViewTransition>{children}</ViewTransition>
      </main>
    </div>
  );
}
