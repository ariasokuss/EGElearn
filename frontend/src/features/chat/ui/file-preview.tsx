"use client"

import { Button } from "@/shared";
// import { LoaderIcon } from "@/shared/assets/icons";
import Image from "next/image";
import { useMemo, useEffect, useRef, useState } from "react";

;

type FilePreviewProps = {
  files: File[]
  onRemove: (index: number) => void
}

function getFileIcon(type: string, name?: string) {
  if (type.startsWith("image/")) return "img"
  if (type === "application/pdf") return "pdf"
  if (type === "text/markdown") return "md"
  if (type === "text/plain") return "txt"
  if (type === "text/csv") return "csv"
  if (type === "application/json") return "json"
  // Fallback: try extension from filename
  const ext = name?.split(".").pop()?.toLowerCase()
  if (ext && ext.length <= 4) return ext
  return "file"
}

export function FilePreview({ files, onRemove }: FilePreviewProps) {
  const prevUrlsRef = useRef<string[]>([])
  const seenKeysRef = useRef<Set<string>>(new Set())
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(new Set());

  const previews = useMemo(
    () =>
      files.map((file) => ({
        key: `${file.name}-${file.size}-${file.lastModified}`,
        name: file.name,
        icon: getFileIcon(file.type, file.name),
        url: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
      })),
    [files],
  );

  useEffect(() => {
    const urls = previews.map((p) => p.url).filter(Boolean) as string[]
    const prev = prevUrlsRef.current
    prevUrlsRef.current = urls

    return () => {
      prev.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [previews])

  useEffect(() => {
    const newKeys = previews
      .map((p) => p.key)
      .filter((key) => !seenKeysRef.current.has(key));

    if (newKeys.length === 0) return;

    newKeys.forEach((key) => seenKeysRef.current.add(key));
    setLoadingKeys((prev) => new Set([...prev, ...newKeys]));

    const timers = newKeys.map((key) =>
      setTimeout(() => {
        setLoadingKeys((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }, 2000),
    );

    return () => timers.forEach(clearTimeout);
  }, [previews]);

  if (files.length === 0) return null

  return (
    <div className="flex gap-2 overflow-x-auto pb-2.5 pt-2">
      {previews.map((preview, i) => {
        const isLoading = loadingKeys.has(preview.key);
        return (
          <div
            key={preview.key}
            className="group relative shrink-0 h-12 w-12 rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-0.5"
          >
            <div
              title={preview.name}
              className="h-full w-full overflow-hidden rounded-[14px] border border-[#E4E4E77A] backdrop-blur-sm"
            >
              {isLoading ? (
                <div className="flex h-full w-full items-center justify-center bg-[var(--ege-surface)]">
                  {/* <LoaderIcon className="animate-spin text-[var(--ege-muted)]" /> */}
                  <svg
                    width="21"
                    height="21"
                    viewBox="0 0 21 21"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M13.7396 2.10324C14.8422 2.52866 15.8503 3.1671 16.7063 3.98211C17.5622 4.79712 18.2492 5.77275 18.7281 6.85328C19.207 7.9338 19.4684 9.09808 19.4973 10.2796C19.5263 11.4612 19.3222 12.6368 18.8968 13.7395C18.4714 14.8422 17.8329 15.8503 17.0179 16.7062C16.2029 17.5622 15.2273 18.2492 14.1468 18.7281C13.0662 19.207 11.902 19.4684 10.7204 19.4973C9.53887 19.5262 8.3632 19.3222 7.26052 18.8967C6.15785 18.4713 5.14976 17.8329 4.29382 17.0179C3.43788 16.2029 2.75085 15.2272 2.27196 14.1467C1.79306 13.0662 1.53168 11.9019 1.50274 10.7204C1.4738 9.53882 1.67787 8.36315 2.10329 7.26047C2.52871 6.15779 3.16715 5.14971 3.98217 4.29376C4.79718 3.43782 5.7728 2.75079 6.85333 2.2719C7.93386 1.79301 9.09813 1.53163 10.2797 1.50269C11.4612 1.47375 12.6369 1.67782 13.7396 2.10324L13.7396 2.10324Z"
                      stroke="#E4E4E7"
                      strokeWidth="3"
                    />
                    <path
                      d="M13.7396 2.10324C14.8422 2.52866 15.8503 3.1671 16.7063 3.98211C17.5622 4.79712 18.2492 5.77275 18.7281 6.85328C19.207 7.9338 19.4684 9.09808 19.4973 10.2796C19.5263 11.4612 19.3222 12.6368 18.8968 13.7395C18.4714 14.8422 17.8329 15.8503 17.0179 16.7062C16.2029 17.5622 15.2273 18.2492 14.1468 18.7281C13.0662 19.207 11.902 19.4684 10.7204 19.4973C9.53887 19.5262 8.3632 19.3222 7.26052 18.8967C6.15785 18.4713 5.14976 17.8329 4.29382 17.0179C3.43788 16.2029 2.75085 15.2272 2.27196 14.1467C1.79306 13.0662 1.53168 11.9019 1.50274 10.7204C1.4738 9.53882 1.67787 8.36315 2.10329 7.26047C2.52871 6.15779 3.16715 5.14971 3.98217 4.29376C4.79718 3.43782 5.7728 2.75079 6.85333 2.2719C7.93386 1.79301 9.09813 1.53163 10.2797 1.50269C11.4612 1.47375 12.6369 1.67782 13.7396 2.10324L13.7396 2.10324Z"
                      stroke="var(--ege-muted)"
                      strokeWidth="3"
                      strokeLinecap="round"
                      pathLength="100"
                      style={{
                        animation:
                          "spinner-rotate 1.4s linear infinite, spinner-dash 1.4s ease-in-out infinite",
                        transformBox: "fill-box",
                        transformOrigin: "center",
                      }}
                    />
                  </svg>
                </div>
              ) : preview.url ? (
                <div className="relative flex h-full w-full items-center justify-center">
                  <Image
                    src={preview.url}
                    alt={preview.name}
                    width={32}
                    height={32}
                    unoptimized
                    className="object-cover rounded-sm"
                  />
                </div>
              ) : (
                <span className="flex h-full w-full items-center justify-center bg-[var(--ege-surface)] nova-text-label-xxs uppercase text-[var(--ege-muted)]">
                  {preview.icon}
                </span>
              )}
            </div>

            <Button
              iconOnly
              size="xxs"
              type="button"
              variant="outline"
              onClick={() => onRemove(i)}
              aria-label="Remove file"
              className="absolute flex items-center justify-center opacity-0 group-hover:opacity-100"
              style={{
                top: 2,
                left: 26,
                padding: "3.33px",
              }}
            >
              <svg
                width="8"
                height="8"
                viewBox="0 0 8 8"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M1 1l6 6M7 1L1 7" />
              </svg>
            </Button>
          </div>
        );
      })}
    </div>
  );
}
