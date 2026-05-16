"use client";

import { Button } from "@/shared";
import { HideBarIcon } from "@/shared/assets/icons";

type ChatHeaderProps = {
  showToggle: boolean;
  isOpen: boolean;
  onToggle: VoidFunction;
};

export function ChatHeader({
  showToggle,
  isOpen,
  onToggle,
}: ChatHeaderProps) {
  return (
    showToggle && (
      <Button
        iconOnly
        variant="plain"
        type="button"
        onClick={onToggle}
        className="flex items-center justify-center transition-all duration-150"
        aria-label={isOpen ? "Hide conversations" : "Show conversations"}
        title={isOpen ? "Hide conversations" : "Show conversations"}
      >
        <HideBarIcon className="h-4 w-4" />
      </Button>
    )
  );
}
