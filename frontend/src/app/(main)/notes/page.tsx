"use client";

import { use, useEffect, useState } from "react";
import { listAllHighlightsApi, type HighlightRead } from "@/features/folder/api/highlights-api";

type PageProps = {
  params: Promise<Record<string, string | string[]>>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function HighlightCard({ item }: { item: HighlightRead }) {
  return (
    <div className="rounded-xl border border-[#F4F4F5] bg-white p-4 flex flex-col gap-2">
      <div className="flex gap-3">
        <div className="w-1 shrink-0 self-stretch rounded-full bg-[#EBDDD5]" />
        <p className="nova-text-label-small text-[#242529]">
          {item.text}
        </p>
      </div>
      {item.comment && (
        <p className="pl-4 nova-text-label-small-regular text-[#72706F]">
          {item.comment}
        </p>
      )}
      <p className="pl-4 nova-text-label-tiny text-[#A1A1AA]">
        {new Date(item.created_at).toLocaleDateString()}
      </p>
    </div>
  );
}

export default function NotesPage({ params, searchParams }: PageProps) {
  use(params);
  use(searchParams);
  const [highlights, setHighlights] = useState<HighlightRead[]>([]);
  const [notes, setNotes] = useState<HighlightRead[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      listAllHighlightsApi("highlight"),
      listAllHighlightsApi("note"),
    ]).then(([h, n]) => {
      setHighlights(h);
      setNotes(n);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-[#71717A]">
        Loading…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 flex flex-col gap-8">
      {highlights.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="nova-text-label-medium text-[#242529]">
            Highlights ({highlights.length})
          </h2>
          {highlights.map((h) => <HighlightCard key={h.id} item={h} />)}
        </section>
      )}

      {notes.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="nova-text-label-medium text-[#242529]">
            Notes ({notes.length})
          </h2>
          {notes.map((n) => <HighlightCard key={n.id} item={n} />)}
        </section>
      )}

      {highlights.length === 0 && notes.length === 0 && (
        <p className="text-center nova-text-p-base text-[#71717A] py-16">
          No highlights or notes yet. Select text in a lesson to save them.
        </p>
      )}
    </div>
  );
}
