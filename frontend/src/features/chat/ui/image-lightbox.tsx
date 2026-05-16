"use client"

import { useEffect, useCallback } from "react"
import { createPortal } from "react-dom"
import Image from "next/image"
import { XMarkIcon } from "@/shared/assets/icons"

type ImageLightboxProps = {
  src: string
  alt?: string
  onClose: () => void
}

export function ImageLightbox({ src, alt, onClose }: ImageLightboxProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    },
    [onClose],
  )

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown)
    // Prevent body scroll while lightbox is open
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", handleKeyDown)
      document.body.style.overflow = ""
    }
  }, [handleKeyDown])

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Close button */}
      <button
        type="button"
        className="absolute top-4 right-4 z-10 flex h-10 w-10 items-center justify-center text-white transition-opacity hover:opacity-70"
        onClick={onClose}
      >
        <XMarkIcon className="h-5 w-5 [&_path]:stroke-white" />
      </button>

      {/* Image */}
      <Image
        src={src}
        alt={alt ?? "Preview"}
        width={1920}
        height={1080}
        className="max-h-[90vh] max-w-[90vw] rounded-lg object-contain"
        unoptimized
        onClick={(e) => e.stopPropagation()}
      />
    </div>,
    document.body,
  )
}
