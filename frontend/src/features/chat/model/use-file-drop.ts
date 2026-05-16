"use client"

import { useState, useRef, useEffect } from "react"

export function useFileDrop() {
  const [isDragging, setIsDragging] = useState(false)
  const dragCountRef = useRef(0)

  useEffect(() => {
    const handleDragEnter = (e: DragEvent) => {
      e.preventDefault()
      dragCountRef.current++
      if (dragCountRef.current === 1) setIsDragging(true)
    }

    const handleDragLeave = (e: DragEvent) => {
      e.preventDefault()
      dragCountRef.current--
      if (dragCountRef.current === 0) setIsDragging(false)
    }

    const handleDrop = (e: DragEvent) => {
      e.preventDefault()
      dragCountRef.current = 0
      setIsDragging(false)
    }

    const handleDragOver = (e: DragEvent) => e.preventDefault()

    document.addEventListener("dragenter", handleDragEnter)
    document.addEventListener("dragleave", handleDragLeave)
    document.addEventListener("dragover", handleDragOver)
    document.addEventListener("drop", handleDrop)

    return () => {
      document.removeEventListener("dragenter", handleDragEnter)
      document.removeEventListener("dragleave", handleDragLeave)
      document.removeEventListener("dragover", handleDragOver)
      document.removeEventListener("drop", handleDrop)
    }
  }, [])

  return { isDragging }
}
