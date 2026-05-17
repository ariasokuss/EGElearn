import { Suspense } from "react";

import { TabsNav, FolderSection } from "@/features/home";

export function HomePage() {
  return (
    <section className="relative min-h-full w-full overflow-hidden px-8 py-8">
      <svg
        aria-hidden="true"
        className="pointer-events-none absolute bottom-[7%] -left-[3%] z-0 h-[220px] w-[106%] text-[#c46b72]"
        viewBox="0 0 1060 220"
        fill="none"
        preserveAspectRatio="none"
      >
        <path
          d="M-80 176C18 124 110 126 166 168C221 210 315 207 340 142C364 80 283 59 265 112C246 169 329 202 398 167C462 134 485 84 552 80C637 74 657 162 728 172C819 185 867 97 950 91C1024 85 1086 118 1164 120C1240 122 1288 84 1360 104"
          stroke="currentColor"
          strokeWidth="12"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>

      <div className="relative z-10">
        <Suspense>
          <TabsNav />
          <FolderSection />
        </Suspense>
      </div>
    </section>
  );
}
