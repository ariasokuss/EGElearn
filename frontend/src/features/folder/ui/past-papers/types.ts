import type { TestSessionOut } from "@/shared/api/generated/model"

export type UploadInfo = {
  id: string
  paper?: File,
  mark?: File
}

export type PastPaperTestInfo = {
  status: "none" | "taking" | "result"
  session?: TestSessionOut
}
