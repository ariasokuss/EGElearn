"use client";

import { useCallback, useRef, useState } from "react";
import { useAuth, useLogout } from "@/features/auth";
import { Button } from "@/shared";
import { getAccessToken } from "@/shared/lib/auth-storage";

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_SIZE = 5 * 1024 * 1024; // 5MB

function displayNameFromEmail(email: string): string {
  const local = email.split("@")[0] ?? email;
  return local.replace(/[._]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const fieldClass =
  "min-w-0 flex-1 rounded-full border border-[var(--ege-border)] bg-[var(--ege-surface)] px-5 py-3 nova-text-label-small text-[var(--ege-text)] transition-shadow placeholder:text-[var(--ege-muted)]";

const fieldClassEditAndChange =
  "min-w-0 flex-1 rounded-full border border-[var(--ege-border)] bg-[var(--ege-surface)] px-5 py-3 nova-text-label-small text-[var(--ege-muted)] transition-shadow";

async function apiFetch(path: string, init?: RequestInit) {
  const token = getAccessToken();
  return fetch(path, {
    ...init,
    headers: {
      ...init?.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

async function apiJson(path: string, body: Record<string, unknown>) {
  return apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

type EditMode = null | "email" | "password";

export function ProfilePanel() {
  const { user } = useAuth();
  const logout = useLogout();
  const email = user?.email ?? "";
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [displayName, setDisplayName] = useState<string | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Edit mode for email / password inline forms
  const [editMode, setEditMode] = useState<EditMode>(null);

  // Email change state
  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailCode, setEmailCode] = useState("");
  const [emailCodeSent, setEmailCodeSent] = useState(false);
  const [emailLoading, setEmailLoading] = useState(false);

  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordLoading, setPasswordLoading] = useState(false);

  const currentName =
    displayName !== null
      ? displayName
      : user?.display_name ?? displayNameFromEmail(email);

  const avatarSrc = avatarPreview ?? user?.avatar_url ?? null;

  const clearMessages = () => { setError(null); setSuccess(null); };

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError("Выбери изображение JPEG, PNG или WebP.");
      return;
    }
    if (file.size > MAX_SIZE) {
      setError("Изображение должно быть меньше 5 МБ.");
      return;
    }
    setError(null);
    setPendingFile(file);
    const url = URL.createObjectURL(file);
    setAvatarPreview(url);
    e.target.value = "";
  }, []);

  const handleApply = useCallback(async () => {
    setSaving(true);
    clearMessages();
    try {
      if (displayName !== null) {
        const res = await apiFetch("/api/v1/users/me", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ display_name: displayName || null }),
        });
        if (!res.ok) throw new Error("Не удалось обновить имя");
      }

      if (pendingFile) {
        const formData = new FormData();
        formData.append("file", pendingFile);
        const uploadRes = await apiFetch("/api/v1/users/me/avatar", {
          method: "POST",
          body: formData,
        });
        if (!uploadRes.ok) throw new Error("Не удалось загрузить аватар");
      }

      window.dispatchEvent(new CustomEvent("auth:tokens-updated"));
      setDisplayName(null);
      setPendingFile(null);
      if (avatarPreview) {
        URL.revokeObjectURL(avatarPreview);
        setAvatarPreview(null);
      }
      setSuccess("Профиль обновлен");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Что-то пошло не так");
    } finally {
      setSaving(false);
    }
  }, [displayName, pendingFile, avatarPreview]);

  // ---- Email change handlers ----

  const handleRequestEmailCode = async () => {
    setEmailLoading(true);
    clearMessages();
    try {
      const res = await apiJson("/api/v1/users/me/email/request", {
        new_email: newEmail,
        password: emailPassword,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? "Не удалось отправить код");
      }
      setEmailCodeSent(true);
      setSuccess("Код отправлен на " + newEmail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Что-то пошло не так");
    } finally {
      setEmailLoading(false);
    }
  };

  const handleConfirmEmailChange = async () => {
    setEmailLoading(true);
    clearMessages();
    try {
      const res = await apiJson("/api/v1/users/me/email/confirm", {
        code: emailCode,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? "Неверный код");
      }
      setSuccess("Email изменен");
      setEditMode(null);
      setNewEmail("");
      setEmailPassword("");
      setEmailCode("");
      setEmailCodeSent(false);
      window.dispatchEvent(new CustomEvent("auth:tokens-updated"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Что-то пошло не так");
    } finally {
      setEmailLoading(false);
    }
  };

  // ---- Password change handler ----

  const handleChangePassword = async () => {
    setPasswordLoading(true);
    clearMessages();
    try {
      const res = await apiJson("/api/v1/users/me/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? "Не удалось изменить пароль");
      }
      setSuccess("Пароль изменен");
      setEditMode(null);
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Что-то пошло не так");
    } finally {
      setPasswordLoading(false);
    }
  };

  const cancelEdit = () => {
    setEditMode(null);
    setNewEmail("");
    setEmailPassword("");
    setEmailCode("");
    setEmailCodeSent(false);
    setCurrentPassword("");
    setNewPassword("");
    clearMessages();
  };

  const hasChanges = displayName !== null || pendingFile !== null;

  return (
    <div className="mx-auto max-w-[760px] px-6 py-8">
      <div className="mt-8 rounded-3xl border border-[var(--ege-border)] bg-[var(--ege-surface)] px-6 py-6 sm:px-8 sm:py-8">
        <h1 className="nova-text-h-xss text-[var(--ege-text)]">
          Профиль
        </h1>
        <div className="mt-4 h-px w-full bg-[var(--ege-border)]" />

        <div className="mt-6 flex items-center gap-4">
          {avatarSrc ? (
            // eslint-disable-next-line @next/next/no-img-element -- blob preview or user avatar URL
            <img
              src={avatarSrc}
              alt="Avatar"
              className="h-16 w-16 shrink-0 rounded-full object-cover"
            />
          ) : (
            <div
              className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-[var(--ege-surface-raised)] nova-text-h-xss text-[var(--ege-text)]"
              aria-hidden
            >
              {email ? email[0]?.toUpperCase() : "?"}
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={handleFileSelect}
          />
          <Button
            variant="plain"
            size="l"
            type="button"
            className="text-[var(--ege-text)] hover:underline"
            onClick={() => fileInputRef.current?.click()}
          >
            Загрузить
          </Button>
        </div>

        {error && (
          <p className="mt-3 nova-text-label-small text-red-500">{error}</p>
        )}
        {success && (
          <p className="mt-3 nova-text-label-small text-emerald-600">{success}</p>
        )}

        <div className="mt-6 flex flex-col gap-4">
          <input
            type="text"
            value={currentName}
            onChange={(e) => setDisplayName(e.target.value)}
            className={fieldClass}
            aria-label="Имя"
            placeholder="Имя"
          />

          {/* ---- Email section ---- */}
          {editMode === "email" ? (
            <div className="flex flex-col gap-3 rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-4">
              <p className="nova-text-label-small text-[var(--ege-muted)]">Изменить email</p>
              {!emailCodeSent ? (
                <>
                  <input
                    type="email"
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    className={fieldClass}
                    placeholder="Новый email"
                    aria-label="Новый email"
                  />
                  <input
                    type="password"
                    value={emailPassword}
                    onChange={(e) => setEmailPassword(e.target.value)}
                    className={fieldClass}
                    placeholder="Текущий пароль"
                    aria-label="Текущий пароль для смены email"
                  />
                  <div className="flex gap-2">
                    <Button
                      variant="default"
                      size="sm"
                      type="button"
                      disabled={!newEmail || !emailPassword || emailLoading}
                      isLoading={emailLoading}
                      onClick={handleRequestEmailCode}
                    >
                      Отправить код
                    </Button>
                    <Button variant="outline" size="sm" type="button" onClick={cancelEdit}>
                      Отмена
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <p className="nova-text-label-small-regular text-[var(--ege-muted)]">
                    Введи 6-значный код, отправленный на <strong>{newEmail}</strong>
                  </p>
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={emailCode}
                    onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    className={fieldClass}
                    placeholder="000000"
                    aria-label="Код подтверждения"
                  />
                  <div className="flex gap-2">
                    <Button
                      variant="default"
                      size="sm"
                      type="button"
                      disabled={emailCode.length !== 6 || emailLoading}
                      isLoading={emailLoading}
                      onClick={handleConfirmEmailChange}
                    >
                      Подтвердить
                    </Button>
                    <Button variant="outline" size="sm" type="button" onClick={cancelEdit}>
                      Отмена
                    </Button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <div className="flex items-stretch gap-3">
              <input
                readOnly
                type="email"
                value={email || "—"}
                className={fieldClassEditAndChange}
                aria-label="Email"
              />
              <Button
                variant="outline"
                size="l"
                type="button"
                className="w-[98px] shrink-0"
                onClick={() => { cancelEdit(); setEditMode("email"); }}
              >
                Изменить
              </Button>
            </div>
          )}

          {/* ---- Password section ---- */}
          {editMode === "password" ? (
            <div className="flex flex-col gap-3 rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-4">
              <p className="nova-text-label-small text-[var(--ege-muted)]">Изменить пароль</p>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className={fieldClass}
                placeholder="Текущий пароль"
                aria-label="Текущий пароль"
              />
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className={fieldClass}
                placeholder="Новый пароль (минимум 8 символов)"
                aria-label="Новый пароль"
              />
              <div className="flex gap-2">
                <Button
                  variant="default"
                  size="sm"
                  type="button"
                  disabled={!currentPassword || newPassword.length < 8 || passwordLoading}
                  isLoading={passwordLoading}
                  onClick={handleChangePassword}
                >
                  Обновить пароль
                </Button>
                <Button variant="outline" size="sm" type="button" onClick={cancelEdit}>
                  Отмена
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-stretch gap-3">
              <input
                readOnly
                type="password"
                value="••••••••"
                className={fieldClassEditAndChange}
                aria-label="Пароль"
              />
              <Button
                variant="outline"
                size="l"
                type="button"
                className="w-[98px] shrink-0"
                onClick={() => { cancelEdit(); setEditMode("password"); }}
              >
                Изменить
              </Button>
            </div>
          )}

          <div className="mt-4 h-px bg-[var(--ege-border)]" />

          <div className="flex items-stretch gap-3">
            <div className={`${fieldClass} flex items-center`}>
              Выйти на этом устройстве
            </div>
            <Button
              variant="outline"
              size="l"
              type="button"
              onClick={logout}
              className="w-[98px] shrink-0"
            >
              Выйти
            </Button>
          </div>
        </div>

        <Button
          type="button"
          size="l"
          className="mt-8 w-full"
          disabled={!hasChanges || saving}
          isLoading={saving}
          onClick={handleApply}
        >
          Сохранить изменения
        </Button>
      </div>
    </div>
  );
}
