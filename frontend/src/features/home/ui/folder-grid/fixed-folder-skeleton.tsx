const SKELETON_COUNT = 3;

function SkeletonCard() {
  return (
    <div
      className="flex h-[138px] w-[230px] shrink-0 flex-col rounded-[18px] border border-[var(--ege-border)] bg-[var(--ege-surface)] p-4"
      aria-hidden
    >
      <div className="mb-3 size-9 animate-pulse rounded-lg bg-[var(--ege-track)]" />
      <div className="h-4 w-24 animate-pulse rounded bg-[var(--ege-track)]" />
    </div>
  );
}

type FixedFolderSkeletonProps = {
  title: string;
};

export function FixedFolderSkeleton({ title }: FixedFolderSkeletonProps) {
  return (
    <div aria-busy="true" aria-live="polite">
      <h1 className="mb-5.5 nova-text-label-base text-[var(--ege-text)]">
        {title}
      </h1>
      <div className="flex flex-wrap gap-3.5">
        {Array.from({ length: SKELETON_COUNT }, (_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    </div>
  );
}
