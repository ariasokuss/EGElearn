"use client";

import { useAuth } from "@/features/auth";
import { Button } from "@/shared";

export function SupportPanel() {
  const { user } = useAuth();
  const email = user?.email ?? "your email";

  return (
    <div className="mx-auto max-w-[760px] px-6 py-8">
      <div
        className="mt-8 rounded-3xl border border-[var(--ege-border)] bg-[var(--ege-surface)] p-8"
      >
        <h1 className="nova-text-h-xss text-[var(--ege-text)]">
          Опиши проблему
        </h1>
        <div className="mt-4 h-px w-full bg-[var(--ege-border)]" />

        <p className="mt-6 nova-text-p-base text-[var(--ege-muted)]">
          Команда NovaLearn ответит на email, указанный при регистрации, в течение 48 часов:{" "}
          <strong className="font-medium text-[var(--ege-text)]">{email}</strong>
        </p>

        <div className="mt-8 flex flex-col gap-6">
          <input
            type="text"
            name="problem-title"
            autoComplete="off"
            className="h-12 w-full rounded-full border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] px-5 nova-text-label-small text-[var(--ege-text)] transition-shadow placeholder:text-[var(--ege-muted)]"
            placeholder="Тема обращения"
          />

          <div className="flex min-h-[200px] flex-col rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-4">
            <textarea
              name="message"
              rows={5}
              className="min-h-[120px] w-full flex-1 resize-none border-0 bg-transparent nova-text-label-small text-[var(--ege-text)] outline-none ring-0 placeholder:text-[var(--ege-muted)] focus-visible:ring-0"
              placeholder="Сообщение..."
            />
            <Button
              size="l"
              type="button"
              className="mt-4 self-start"
            >
              Отправить
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
