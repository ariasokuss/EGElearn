import { Suspense } from "react";

import { TabsNav, FolderSection } from "@/features/home";

export function HomePage() {
  return (
    <section className="w-full px-7 py-7">
      <Suspense>
        <TabsNav />
        <FolderSection />
      </Suspense>
    </section>
  );
}
