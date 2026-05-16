type UploadTarget = "paper" | "mark_scheme"

const uploadTargetCopy: Record<UploadTarget, string> = {
  paper: "file",
  mark_scheme: "mark scheme",
}

export function getUploadErrorMessage(status: number | null, target: UploadTarget): string {
  const subject = uploadTargetCopy[target]

  if (status === 413) return `The ${subject} is too large. Maximum upload size is 15 MB.`
  if (status === 401) return `You need to sign in again to upload this ${subject}.`
  if (status === 403) return `You do not have permission to upload this ${subject}.`
  if (status === 422) return `The ${subject} format is not supported. Please upload a valid PDF.`
  if (status === 429) return "Too many upload attempts. Please wait a bit and retry."
  if (status !== null && status >= 500) return "Upload failed due to a server error. Please retry."

  return "Upload failed. Please try again."
}
