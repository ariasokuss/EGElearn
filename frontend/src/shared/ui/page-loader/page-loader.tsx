type PageLoaderProps = {
  showText?: boolean;
};

export function PageLoader({ showText = true }: PageLoaderProps) {
  return (
    <div className="fixed inset-0 flex flex-col items-center justify-center gap-4 bg-[var(--ege-canvas)] text-[var(--ege-text)]">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--ege-muted)] border-t-transparent" />
      {showText && (
        <p className="nova-text-label-small text-[var(--ege-muted)]">
          wait a second
        </p>
      )}
    </div>
  );
}
