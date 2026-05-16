"use client";

export function TermsPanel() {
  return (
    <div className="mx-auto max-w-[720px] px-6 py-8">
      <div
        className="mt-8 rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface)] px-[20px] pt-[16px] pb-6"
      >
        <h1 className="nova-text-h-xss text-[var(--ege-text)]">
          Условия и приватность
        </h1>

        <div className="mt-6 border-t border-[var(--ege-border)]">
          <section className="py-4">
            <h2 className="nova-text-label-medium text-[var(--ege-text)]">
              Условия использования
            </h2>
            <p className="mt-1 nova-text-p-base text-[var(--ege-muted)]">
              Правила доступа к продукту, подпискам и допустимому использованию.
            </p>
          </section>
          <section className="pt-2">
            <h2 className="nova-text-label-medium text-[var(--ege-text)]">
              Политика приватности
            </h2>
            <p className="mt-1 nova-text-p-base text-[var(--ege-muted)]">
              Как мы собираем, храним и обрабатываем персональные данные.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
