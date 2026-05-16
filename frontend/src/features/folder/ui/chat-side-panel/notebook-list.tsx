"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useNotes, type Note } from "../../model/notes-context";
import { NoteIcon } from "@/shared/assets/icons";

type NotebookListProps = {
  notes: Note[];
  onDelete: (id: string) => void;
  onUpdateComment: (id: string, comment: string) => void;
  onSelect?: (note: Note) => void;
};

function NoteItem({
  note,
  onUpdateComment,
  onSelect,
}: {
  note: Note;
  onUpdateComment: (id: string, comment: string) => void;
  onSelect?: (note: Note) => void;
}) {
  const { pendingFocusNoteId, consumePendingFocus } = useNotes();
  const shouldFocusOnMountRef = useRef(pendingFocusNoteId === note.id);
  const [editing, setEditing] = useState(() => shouldFocusOnMountRef.current);
  const [draft, setDraft] = useState(note.comment ?? "");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!shouldFocusOnMountRef.current) return;
    consumePendingFocus();
    requestAnimationFrame(() => inputRef.current?.focus());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleStartEdit = useCallback(() => {
    setDraft(note.comment ?? "");
    setEditing(true);
    requestAnimationFrame(() => {
      inputRef.current?.focus()
      const len = note.comment?.length ?? 0
      inputRef.current?.setSelectionRange(len, len);
  });
  }, [note.comment]);

  const handleSave = useCallback(() => {
    const trimmed = draft.trim();
    onUpdateComment(note.id, trimmed);
    setEditing(false);
  }, [draft, note.id, onUpdateComment]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSave();
      }
      if (e.key === "Escape") {
        setDraft(note.comment ?? "");
        setEditing(false);
      }
    },
    [handleSave, note.comment],
  );

  return (
    <div className="p-3.5 gap-0.5">
      <div className="flex gap-3">
        <div className="w-1 shrink-0 self-stretch rounded-full bg-[#EBDDD5]" />

        {onSelect ? (
          <button
            type="button"
            onClick={() => onSelect(note)}
            className="text-left nova-text-label-small text-[#242529] hover:text-[#7C6F68] transition-colors"
          >
            {note.text}
          </button>
        ) : (
          <p className="nova-text-label-small text-[#242529]">
            {note.text}
          </p>
        )}
      </div>

      <div className="flex gap-1.5 pt-2 px-3.5">
        <NoteIcon className="mt-0.5 shrink-0" />

        {editing ? (
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            rows={1}
            className="mt-px flex-1 resize-none border-none bg-transparent p-0 nova-text-label-small-regular text-[#242529] outline-none placeholder:text-[#A1A1AA]"
            placeholder="Add a comment…"
          />
        ) : (
          <button
            type="button"
            onClick={handleStartEdit}
            className="text-left nova-text-label-small-regular text-[#72706F] hover:text-[#242529] transition-colors"
          >
            {note.comment || "Add a comment…"}
          </button>
        )}
      </div>
    </div>
  );
}

export function NotebookList({ notes, onUpdateComment, onSelect }: NotebookListProps) {
  if (notes.length === 0) {
    return (
      <p className="py-16 text-center nova-text-p-base text-[#71717A]">
        No notes yet. Select text in a lesson.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <p className="nova-text-label-medium text-[#242529] mb-1.5">
        Highlights ({notes.length})
      </p>
      <div className="flex flex-col gap-1.5">
        {notes.map((note, i) => (
          <div key={note.id}>
            {i > 0 && <div className="h-px bg-[#F4F4F5]" />}
            <NoteItem note={note} onUpdateComment={onUpdateComment} onSelect={onSelect} />
          </div>
        ))}
      </div>
    </div>
  );
}
