import { MAX_FILES, MAX_SIZE_MB, MAX_PDF_SIZE_MB, ACCEPTED_FILE_TYPES } from "./constants"

const MAX_BYTES = MAX_SIZE_MB * 1024 * 1024
const MAX_PDF_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024

function isAcceptedType(type: string): boolean {
  return ACCEPTED_FILE_TYPES.some((t) => type.startsWith(t))
}

function maxBytesForFile(file: File): number {
  if (file.type === "application/pdf") return MAX_PDF_BYTES
  return MAX_BYTES
}

/**
 * Validate and filter files for attachment.
 *
 * @param newFiles   Files the user wants to add
 * @param existing   Files already attached (used to enforce MAX_FILES limit)
 * @param checkType  Whether to filter by MIME type (true for drag-drop, false for file input which uses `accept`)
 */
export function validateFiles(
  newFiles: File[] | FileList,
  existing: File[] = [],
  checkType = false,
): File[] {
  const remaining = MAX_FILES - existing.length
  if (remaining <= 0) return []

  let files = Array.from(newFiles).filter((f) => f.size <= maxBytesForFile(f))

  if (checkType) {
    files = files.filter((f) => isAcceptedType(f.type))
  }

  return files.slice(0, remaining)
}
