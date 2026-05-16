"use client";

type UsageRowProps = {
  title: string;
  periodLabel: string;
  used: number;
  total: number;
  unit: string;
  remainingLabel: string;
};

function UsageRow({ title, periodLabel, used, total, unit, remainingLabel }: UsageRowProps) {
  const pct = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;
  return (
    <div className="border-b border-[var(--ege-border)] py-5 last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="nova-text-label-small text-[var(--ege-text)]">
            {title}
          </p>
          <p className="mt-1 nova-text-label-small-regular text-[var(--ege-muted)]">
            {periodLabel}
          </p>
        </div>
        <div className="text-right">
          <p className="nova-text-label-small text-[var(--ege-text)]">
            {used} / {total} {unit}
          </p>
          <p className="mt-1 nova-text-label-small-regular text-[var(--ege-muted)]">
            {remainingLabel}
          </p>
        </div>
      </div>
      <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-[var(--ege-track)]">
        <div
          className="h-full rounded-full bg-[var(--ege-accent)]"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function LimitsPanel() {
  return (
    <div className="mx-auto max-w-[720px] px-6 p-8">
      <div className="mt-8 rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface)] p-8">
        <h1 className="nova-text-h-xss text-[var(--ege-text)]">
          Лимиты
        </h1>
        <div className="mt-4 h-px bg-[var(--ege-border)]" />
        <UsageRow
          title="Сообщения в чате"
          periodLabel="Месяц"
          used={224}
          total={1000}
          unit="сообщений"
          remainingLabel="Осталось 776 сообщений"
        />
        <UsageRow
          title="Генерации тестов"
          periodLabel="Месяц"
          used={47}
          total={200}
          unit="тестов"
          remainingLabel="Осталось 153 теста"
        />
      </div>
    </div>
  );
}
