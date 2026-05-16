import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/shared";

export const metadata: Metadata = {
  title: "Page not found",
  robots: { index: false, follow: true },
};

export default function NotFound() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-6 py-16">
      <div className="flex w-full max-w-md flex-col items-center rounded-2xl border border-[#E8E5E1] bg-white px-8 py-10 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.04),0px_2px_4px_-2px_rgba(0,0,0,0.02)]">
        <p className="nova-text-label-small font-semibold uppercase tracking-wide text-[#71717A]">
          404
        </p>
        <h1 className="mt-2 text-center nova-text-h-small text-[#242529]">
          Page not found
        </h1>
        <p className="mt-3 text-center nova-text-p-base text-[#71717A]">
          This link may be broken or the page may have been moved. You can go back to NovaLearn and continue from there.
        </p>
        <Button asChild size="l" variant="outline" className="mt-8">
          <Link href="/">Back to home</Link>
        </Button>
      </div>
    </div>
  );
}
