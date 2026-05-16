"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";

import type { HighlightRead } from "../api/highlights-api";
import {
  createHighlightApi,
  deleteHighlightApi,
  listLessonHighlightsApi,
  patchHighlightApi,
} from "../api/highlights-api";

export type Note = HighlightRead & { lessonId: string };

function toNote(h: HighlightRead): Note {
  return { ...h, lessonId: h.lesson_id };
}

function makeOptimistic(text: string, lessonId: string): Note {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    user_id: "",
    lesson_id: lessonId,
    lessonId,
    text,
    comment: null,
    type: "highlight",
    created_at: now,
    updated_at: now,
  };
}

type NotesContextValue = {
  notes: Note[];
  addNote: (text: string, lessonId: string) => Note;
  addNoteWithFocus: (text: string, lessonId: string) => Note;
  removeNote: (id: string) => void;
  updateNoteComment: (id: string, comment: string) => void;
  pendingFocusNoteId: string | null;
  consumePendingFocus: () => void;
  loadForLesson: (lessonId: string) => Promise<void>;
};

const NotesContext = createContext<NotesContextValue | null>(null);

export function NotesProvider({
  children,
}: {
  folderId: string;
  children: React.ReactNode;
}) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [pendingFocusNoteId, setPendingFocusNoteId] = useState<string | null>(null);
  const loadedLessons = useRef(new Set<string>());
  // Stores removed notes keyed by id for rollback on API failure
  const removedRef = useRef<Map<string, Note>>(new Map());
  // Maps optimistic (client-generated) IDs to real server IDs
  // Kept indefinitely so PATCH/DELETE always resolve to the real ID
  const idMapRef = useRef<Map<string, string>>(new Map());

  const loadForLesson = useCallback(async (lessonId: string) => {
    if (loadedLessons.current.has(lessonId)) return;
    loadedLessons.current.add(lessonId);
    const highlights = await listLessonHighlightsApi(lessonId);
    setNotes((prev) => {
      // Exclude server IDs already represented by an optimistic entry
      const mappedServerIds = new Set(idMapRef.current.values());
      const existingIds = new Set(prev.map((n) => n.id));
      const newOnes = highlights
        .filter((h) => !existingIds.has(h.id) && !mappedServerIds.has(h.id))
        .map(toNote);
      return [...prev, ...newOnes];
    });
  }, []);

  const addNote = useCallback((text: string, lessonId: string): Note => {
    const optimistic = makeOptimistic(text, lessonId);
    setNotes((prev) => [optimistic, ...prev]);

    createHighlightApi(lessonId, text).then((h) => {
      if (!h) {
        setNotes((prev) => prev.filter((n) => n.id !== optimistic.id));
        return;
      }
      // Store mapping so PATCH/DELETE resolve to the real server ID
      idMapRef.current.set(optimistic.id, h.id);
      // Keep the optimistic ID as the React key — avoids remounting NoteItem
      // (which would steal focus from an in-progress comment edit)
      setNotes((prev) =>
        prev.map((n) =>
          n.id === optimistic.id
            ? { ...toNote(h), id: optimistic.id, lessonId }
            : n,
        ),
      );
    });

    return optimistic;
  }, []);

  const addNoteWithFocus = useCallback(
    (text: string, lessonId: string): Note => {
      const note = addNote(text, lessonId);
      setPendingFocusNoteId(note.id);
      return note;
    },
    [addNote],
  );

  const consumePendingFocus = useCallback(() => {
    setPendingFocusNoteId(null);
  }, []);

  const removeNote = useCallback((id: string) => {
    const serverId = idMapRef.current.get(id) ?? id;
    setNotes((prev) => {
      const note = prev.find((n) => n.id === id);
      if (note) removedRef.current.set(id, note);
      return prev.filter((n) => n.id !== id);
    });

    deleteHighlightApi(serverId).then((ok) => {
      const saved = removedRef.current.get(id);
      removedRef.current.delete(id);
      if (!ok && saved) {
        setNotes((prev) => [...prev, saved]);
      }
    });
  }, []);

  const updateNoteComment = useCallback((id: string, comment: string) => {
    const serverId = idMapRef.current.get(id) ?? id;
    const normalised = comment || null;
    // Optimistic update — compute type locally to match backend logic
    setNotes((prev) =>
      prev.map((n) =>
        n.id === id
          ? { ...n, comment: normalised, type: normalised ? "note" : "highlight" }
          : n,
      ),
    );

    // Fire-and-forget: sync updated_at from server response, keep client ID
    patchHighlightApi(serverId, normalised).then((updated) => {
      if (!updated) return;
      setNotes((prev) =>
        prev.map((n) =>
          n.id === id ? { ...toNote(updated), id, lessonId: n.lessonId } : n,
        ),
      );
    });
  }, []);

  return (
    <NotesContext
      value={{
        notes,
        addNote,
        addNoteWithFocus,
        removeNote,
        updateNoteComment,
        pendingFocusNoteId,
        consumePendingFocus,
        loadForLesson,
      }}
    >
      {children}
    </NotesContext>
  );
}

export function useNotes() {
  const ctx = useContext(NotesContext);
  if (!ctx) throw new Error("useNotes must be used within NotesProvider");
  return ctx;
}
