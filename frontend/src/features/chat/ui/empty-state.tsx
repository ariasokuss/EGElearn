type EmptyStateProps = {
  onSuggestionClick: (prompt: string) => void
}

export function EmptyState({ onSuggestionClick }: EmptyStateProps) {
  void onSuggestionClick

  return (
    <div className="flex items-center justify-center px-4">
      <h2 className="text-center nova-text-h-small text-[var(--ege-text)]">
        Что разберём сегодня?
      </h2>
    </div>
  )
}
