"use client";

import Link from "next/link";
import { trackSeoEvent } from "@/shared/lib";

type SeoCtaLinkProps = {
  href: string;
  text: string;
  eventName: string;
  eventLocation: string;
};

export function SeoCtaLink({ href, text, eventName, eventLocation }: SeoCtaLinkProps) {
  return (
    <Link
      href={href}
      onClick={() => trackSeoEvent(eventName, { location: eventLocation, href })}
      className="inline-flex items-center justify-center rounded-xl bg-[#242529] px-4 py-2 font-inter text-sm font-medium text-white transition hover:opacity-90"
    >
      {text}
    </Link>
  );
}
