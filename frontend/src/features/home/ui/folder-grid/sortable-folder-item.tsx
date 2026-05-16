"use client";

import { memo, useCallback } from "react";

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { FolderItem } from "./folder-item";

type SortableFolderItemProps = {
  id: string;
  name: string;
  pressed?: boolean;
  showSeparatorAfter?: boolean;
  isDraggingAny?: boolean;
  onRename?: (id: string, name: string) => void;
  readOnly?: boolean;
  onClick?: VoidFunction;
};

export const SortableFolderItem = memo(function SortableFolderItem({
  id,
  name,
  pressed,
  showSeparatorAfter,
  isDraggingAny,
  onRename,
  readOnly = false,
  onClick,
}: SortableFolderItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });

  const resolvedTransition =
    transition ?? (isDraggingAny && !isDragging ? "transform 250ms ease" : undefined);

  const dragHandleProps = {
    ...attributes,
    ...(listeners ?? {}),
  } as React.HTMLAttributes<HTMLButtonElement>;

  const handleRename = useCallback(
    (name: string) => onRename?.(id, name),
    [id, onRename],
  );

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition: resolvedTransition,
        opacity: isDragging ? 0 : 1,
      }}
      className="relative"
    >
      <FolderItem
        name={name}
        onRename={onRename ? handleRename : undefined}
        pressed={pressed}
        dragHandleProps={dragHandleProps}
        readOnly={readOnly}
        onClick={onClick}
      />
      {showSeparatorAfter && (
        <div
          className="pointer-events-none absolute top-0 z-10 h-full w-0.75 rounded-full bg-[#3B82F666]"
          style={{ left: "calc(100% + 4.5px)" }}
        />
      )}
    </div>
  );
});
