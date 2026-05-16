"use client";

import { useCallback, useRef, useState } from "react";

import { EditFolderIcon, FolderIcon } from "@/shared/assets/icons";

import { FolderCard } from "./folder-card";
import { Button } from "@/shared";

type FolderItemProps = {
  name: string;
  onRename?: (name: string) => void;
  onClick?: VoidFunction;
  pressed?: boolean;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
  readOnly?: boolean;
};

export function FolderItem({
  name: initialName,
  onRename,
  onClick,
  pressed,
  dragHandleProps,
  readOnly = false,
}: FolderItemProps) {
  const [label, setLabel] = useState(initialName);
  const [editing, setEditing] = useState(false);
  const savedLabel = useRef(label);
  const skipBlur = useRef(false);

  if (!editing && label !== initialName) {
    setLabel(initialName);
  }

  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    savedLabel.current = label;
    setEditing(true);
  };

  const commitEdit = useCallback(() => {
    setEditing(false);
    onRename?.(label);
  }, [label, onRename]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      skipBlur.current = true;
      commitEdit();
    } else if (e.key === "Escape") {
      skipBlur.current = true;
      setLabel(savedLabel.current);
      setEditing(false);
    }
  };

  const handleBlur = () => {
    if (skipBlur.current) {
      skipBlur.current = false;
      return;
    }
    commitEdit();
  };

  return (
    <div className="group relative">
      <FolderCard
        onClick={onClick}
        pressed={pressed}
        dragHandleProps={dragHandleProps}
      >
        <div className="flex h-full flex-col justify-between">
          <FolderIcon pressed={pressed} className="h-[64px] w-[82px]" />
          {editing ? (
            <input
              autoFocus
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              onBlur={handleBlur}
              onKeyDown={handleKeyDown}
              onFocus={(e) => {
                const len = e.target.value.length;
                e.target.setSelectionRange(len, len);
              }}
              onClick={(e) => e.stopPropagation()}
              placeholder="Введите название"
              className="w-full border-none bg-transparent nova-text-label-small text-[var(--ege-text)] outline-none placeholder:text-[var(--ege-muted)]"
            />
          ) : (
            <span className="nova-text-label-small text-[var(--ege-text)]">
              {label || (
                <span className="text-[var(--ege-muted)]">
                  Введите название
                </span>
              )}
            </span>
          )}
        </div>
      </FolderCard>
      {!readOnly && (
        <Button
          iconOnly
          rounded={false}
          variant="plain"
          type="button"
          className="absolute top-2 right-2.5 flex items-center justify-center opacity-0 group-hover:opacity-100"
          onClick={startEdit}
        >
          <EditFolderIcon />
        </Button>
      )}
    </div>
  );
}
