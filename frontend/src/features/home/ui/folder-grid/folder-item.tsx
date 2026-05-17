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
        <div className="relative flex h-full w-full flex-col justify-end">
          <div className="relative">
            <FolderIcon
              pressed={pressed}
              className="h-[132px] w-[170px] drop-shadow-[0px_10px_16px_rgba(11,15,26,0.12)] transition-transform duration-300 group-hover/card:-translate-y-0.5"
            />
          </div>
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
              placeholder="Enter the name"
              className="absolute bottom-5 left-5 z-10 w-[132px] border-none bg-transparent nova-text-label-small text-[#0b0f1a] outline-none placeholder:text-[#5b6472]"
            />
          ) : (
            <span className="absolute bottom-5 left-5 z-10 max-w-[132px] whitespace-normal break-words nova-text-label-small font-semibold text-[#0b0f1a]">
              {label || (
                <span className="text-[#5b6472]">
                  Enter the name
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
