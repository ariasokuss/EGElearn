import { CreateFolderCard } from "./create-folder-card";

const SKELETON_COUNT = 2;

function SkeletonCard() {
  return (
    <div
      className="flex h-[160px] w-[260px] shrink-0 flex-col rounded-[22px] border border-[var(--ege-border)] bg-[var(--ege-surface)] p-5"
      aria-hidden
    >
      <div className="mb-3 size-9 animate-pulse rounded-lg bg-[var(--ege-track)]" />
      <div className="h-4 w-24 animate-pulse rounded bg-[var(--ege-track)]" />
    </div>
  );
}

type FolderGridSkeletonProps = {
  onCreateFolder: VoidFunction;
};

export function FolderGridSkeleton({ onCreateFolder }: FolderGridSkeletonProps) {
  return (
    <div>
      <h1 className="mb-5.5 nova-text-label-base text-[var(--ege-text)]">
        My folders
      </h1>
      <div className="flex flex-wrap gap-3">
        <CreateFolderCard onCreateFolder={onCreateFolder} />
        {Array.from({ length: SKELETON_COUNT }, (_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    </div>
  );
}
