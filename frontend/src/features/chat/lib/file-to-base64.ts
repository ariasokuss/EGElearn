/**
 * Convert a File to a base64 data URL string.
 */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

/**
 * Read raw base64 (no data-URI prefix) from a File.
 */
function fileToRawBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      // Strip data-URI prefix: "data:<mime>;base64,"
      const commaIdx = result.indexOf(",")
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result)
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

/**
 * Convert an array of image files to base64 data-URI strings.
 * Non-image files are skipped.
 */
export async function imagesToBase64(files: File[]): Promise<string[]> {
  const imageFiles = files.filter(
    (f) => f.type.startsWith("image/") && !isHeic(f),
  )
  return Promise.all(imageFiles.map(fileToBase64))
}

export type FileAttachmentPayload = {
  filename: string
  data: string
  mime_type: string
}

function isHeic(file: File): boolean {
  const t = file.type.toLowerCase()
  if (t === "image/heic" || t === "image/heif") return true
  // iOS sometimes reports empty type for HEIC
  const ext = file.name.toLowerCase()
  return ext.endsWith(".heic") || ext.endsWith(".heif")
}

function effectiveMime(file: File): string {
  if (isHeic(file)) return "image/heic"
  if (file.type === "text/x-markdown") return "text/markdown"
  if (file.type) return file.type
  // Guess from extension
  const ext = file.name.split(".").pop()?.toLowerCase()
  if (ext === "md") return "text/markdown"
  if (ext === "txt") return "text/plain"
  if (ext === "pdf") return "application/pdf"
  return "application/octet-stream"
}

/**
 * Convert non-standard-image files (PDFs, text, HEIC) to attachment payloads
 * for the backend `attachments` field.
 */
export async function filesToAttachments(
  files: File[],
): Promise<FileAttachmentPayload[]> {
  const attachmentFiles = files.filter(
    (f) => !f.type.startsWith("image/") || isHeic(f),
  )
  return Promise.all(
    attachmentFiles.map(async (f) => ({
      filename: f.name,
      data: await fileToRawBase64(f),
      mime_type: effectiveMime(f),
    })),
  )
}
