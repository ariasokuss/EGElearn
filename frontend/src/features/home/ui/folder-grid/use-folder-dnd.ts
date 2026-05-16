import { useCallback, useEffect, useMemo, useState } from "react";

import {
  DragEndEvent,
  DragOverEvent,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { arrayMove } from "@dnd-kit/sortable";

import type { FolderOut } from "@/shared/api/generated/model";

const POINTER_SENSOR_OPTIONS = { activationConstraint: { distance: 8 } };

type UseFolderDndOptions = {
  folders: FolderOut[];
  setFolders: React.Dispatch<React.SetStateAction<FolderOut[]>>;
  onOrderChange?: (orderedIds: string[]) => void | Promise<void>;
};

export function useFolderDnd({
  folders,
  setFolders,
  onOrderChange,
}: UseFolderDndOptions) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [justDroppedId, setJustDroppedId] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, POINTER_SENSOR_OPTIONS));

  const handleDragStart = useCallback(({ active }: DragStartEvent) => {
    setActiveId(active.id as string);
    setJustDroppedId(null);
  }, []);

  const handleDragOver = useCallback(({ over }: DragOverEvent) => {
    setOverId(over ? (over.id as string) : null);
  }, []);

  const handleDragEnd = useCallback(
    ({ active, over }: DragEndEvent) => {
      setActiveId(null);
      setOverId(null);
      if (over && active.id !== over.id) {
        setFolders((prev) => {
          const oldIndex = prev.findIndex((f) => f.id === active.id);
          const newIndex = prev.findIndex((f) => f.id === over.id);
          const next = arrayMove(prev, oldIndex, newIndex);
          queueMicrotask(() => {
            void onOrderChange?.(next.map((f) => f.id));
          });
          return next;
        });
      }
      setJustDroppedId(active.id as string);
    },
    [setFolders, onOrderChange]
  );

  useEffect(() => {
    if (!justDroppedId) return;
    const clearSelection = () => setJustDroppedId(null);
    document.addEventListener("pointerdown", clearSelection);
    return () => document.removeEventListener("pointerdown", clearSelection);
  }, [justDroppedId]);

  const separatorAfterIndex = useMemo((): number => {
    if (!activeId || !overId || activeId === overId) return -1;
    const ai = folders.findIndex((f) => f.id === activeId);
    const oi = folders.findIndex((f) => f.id === overId);
    return ai < oi ? oi : oi - 1;
  }, [activeId, overId, folders]);

  const activeFolder = useMemo(
    () => folders.find((f) => f.id === activeId) ?? null,
    [folders, activeId],
  );

  const folderIds = useMemo(() => folders.map((f) => f.id), [folders]);

  return {
    folders,
    setFolders,
    activeId,
    activeFolder,
    separatorAfterIndex,
    justDroppedId,
    sensors,
    folderIds,
    handlers: {
      onDragStart: handleDragStart,
      onDragOver: handleDragOver,
      onDragEnd: handleDragEnd,
    },
  };
}
