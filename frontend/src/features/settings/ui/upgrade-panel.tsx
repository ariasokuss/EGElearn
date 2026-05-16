"use client";

import { Button } from "@/shared";
import { MarkIcon } from "@/shared/assets/icons";

const COMPARISON_ROWS: { label: string; values: [string, string, string] }[] = [
  {
    label: "Доступ к урокам",
    values: [
      "1 тема на предмет",
      "Все темы по всем предметам",
      "Все темы по всем предметам",
    ],
  },
  {
    label: "Сообщения в чате",
    values: ["50", "300 в месяц", "800 в месяц"],
  },
  {
    label: "Feynman",
    values: ["60 в месяц", "60 в месяц", "150 в месяц"],
  },
  {
    label: "Свои тесты",
    values: ["60 в месяц", "25", "75"],
  },
  {
    label: "Тесты Nova на предмет",
    values: ["1", "3", "5"],
  },
  {
    label: "Архивные работы",
    values: ["2", "3 на предмет", "Безлимит"],
  },
];

const PLANS = [
  {
    name: "Бесплатный",
    priceLine: "Бесплатно",
    subtitle: "Начать подготовку к ЕГЭ",
    cta: "Текущий тариф",
    ctaStyle: "muted" as const,
  },
  {
    name: "Plus",
    priceLine: "12 $ в месяц",
    subtitle: "Больше практики и объяснений",
    cta: "Выбрать Plus",
    ctaStyle: "primary" as const,
  },
  {
    name: "Pro",
    priceLine: "17 $ в месяц",
    subtitle: "Максимум подготовки",
    cta: "Выбрать Pro",
    ctaStyle: "primary" as const,
  },
];

export function UpgradePanel() {
  return (
    <div className="mx-auto max-w-[1000px] px-6 py-8">
      <div className="mt-8 rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface)] px-[8px] pt-[16px]">
        <h1 className="mx-[16px] mt-[12px] nova-text-h-tiny text-[var(--ege-text)]">
          Тарифы
        </h1>

        <div className="mt-7 mb-[8px] grid grid-cols-1 gap-2.5 sm:gap-2.5 lg:grid-cols-3">
          {PLANS.map((plan, colIndex) => (
            <div
              key={plan.name}
              className="flex h-full min-h-0 flex-col rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-6"
            >
              <header className="shrink-0">
                <p className="nova-text-label-base font-semibold text-[var(--ege-text)]">
                  {plan.name}
                </p>
                
                <p className="mt-2 nova-text-h-xss text-[var(--ege-text)]">
                  {plan.priceLine}
                </p>
                
                <p className="mt-1 nova-text-label-small-regular text-[var(--ege-muted)]">
                  {plan.subtitle}
                </p>
                <div className="mx-4 mt-4 h-[1px] bg-[var(--ege-border)]" />
              </header>

              <div className="mt-4 flex min-h-0 flex-1 flex-col gap-5">
                {COMPARISON_ROWS.map((row) => (
                  <div key={row.label}>
                    <p className="nova-text-label-small text-[var(--ege-text)]">
                      {row.label}
                    </p>
                    <div className="mt-1.5 flex items-center gap-2">
                      <MarkIcon
                        className="shrink-0"
                        alt=""
                        width={15}
                        height={15}
                        aria-hidden
                      />
                      <span className="nova-text-label-small-regular text-[var(--ege-muted)]">
                        {row.values[colIndex]}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mx-4 mt-6 h-[1px] bg-[var(--ege-border)]" />

              <div className="mt-auto pt-6">
                <Button
                  variant={plan.ctaStyle === "muted" ? "outline" : "default"}
                  type="button"
                  disabled={plan.ctaStyle === "muted"}
                  className={plan.ctaStyle === "muted" ? "cursor-default disabled:opacity-100" : ""}
                >
                  {plan.cta}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
