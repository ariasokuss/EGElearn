import { PlusIcon } from "@/shared/assets/icons";

import { FolderCard } from "./folder-card";

type CreateFolderCardProps = {
  onCreateFolder: VoidFunction;
};

export function CreateFolderCard({ onCreateFolder }: CreateFolderCardProps) {
  return (
    <FolderCard onClick={onCreateFolder}>
      <div className="flex h-full items-center justify-center gap-1">
        <PlusIcon className="shrink-0 text-[var(--ege-muted)]" />
        <span className="nova-text-label-small text-[var(--ege-text)]">
          Create folder
        </span>
      </div>
    </FolderCard>
  );
}
