"use client";

import { deleteMarkSchemeApiV1PastPapersPastPaperIdMarkSchemeDelete, deletePastPaperApiV1PastPapersPastPaperIdDelete, listPastPapersApiV1PastPapersGet, uploadMarkSchemeApiV1PastPapersPastPaperIdMarkSchemePost } from "@/shared/api";
import type { PastPaperListOut } from "@/shared/api/generated/model";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { UploadInfo } from "../ui/past-papers/types";
import { getPastPaperStatus, streamPastPaperUpload } from "../api/past-papers-api";
import { getHttpStatus } from "@/shared/api/http-error";
import { notify } from "@/shared/lib/notify";
import { useRouter } from "next/navigation";

export type MarkState = {
  name: string,
  status: "completed"
} | {
  name?: never
  status: "none" | "waiting" | "processing" | "failed"
}

export type PastPaperUserInfo = {
  id: string,
  title: string,
  percent?: number
  status: "processing" | "ready" | "failed",
  paperFailureStatus?: number | null
  markFailureStatus?: number | null
  markState: MarkState,
  processingPhase?: "ocr" | "mark_scheme_parsing" | "parsing" | "mark_scheme_matching" | "matching" | null
}

type PastPaperNovaInfo = {
  id: string,
  title: string,
  percent?: number
  status: "ready"
}

type PastPaperFileInfo = {
  paperFile?: File,
  markFile?: File,
  attachingMarkFile?: boolean,
  newId?: string
}

type PastPapersContextValue = {
  pastPapersUser: PastPaperUserInfo[]
  pastPapersNova: PastPaperNovaInfo[]
  loading: boolean
  uploadPaper(paperId: string): void,
  attachMark(paperId: string, file?: File): void
  removeMark(paperId: string): void,
  removePaper(paperId: string): void,
  attachingMark(paperId: string): void,
  removeAttachingMark(paperId: string): void,
  addPapersToUpload(...papers: UploadInfo[]): void
  renamePaper(paperId: string, title: string): void
};

const PastPapersContext = createContext<PastPapersContextValue | null>(null);

// Module-level: lets a background uploadPaper (running after component unmount)
// trigger a re-fetch in whatever PastPapersProvider is currently mounted for the folder.
const _folderRefreshFns = new Map<string, () => void>()
const _pendingRefreshFolders = new Set<string>()

function _triggerFolderRefresh(folderId: string): void {
  const fn = _folderRefreshFns.get(folderId)
  if (fn) fn()
  else _pendingRefreshFolders.add(folderId)
}

type PastPapersProviderProps = {
  children: React.ReactNode
  folderId: string
}

export function PastPapersProvider({ children, folderId }: PastPapersProviderProps) {
  const router = useRouter()

  const [pastPapersUser, setPastPapersUser] = useState<PastPaperUserInfo[]>([])
  const [pastPapersNova, setPastPapersNova] = useState<PastPaperNovaInfo[]>([])
  const [loading, setLoading] = useState(true)

  const paperUploadList = useRef<Map<string, PastPaperFileInfo>>(new Map())
  const attachMarkAfterUpload = useRef<{ id: string, file: File }>(null)
  // Map from paperId → interval handle; replaces the old pollingIds Set so we can
  // clear all intervals on unmount and avoid the network-request leak.
  const pollingMap = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map())
  const isMountedRef = useRef(true)

  const pollPaperStatus = useCallback((paperId: string) => {
    if (pollingMap.current.has(paperId)) return

    const interval = setInterval(async () => {
      try {
        const s = await getPastPaperStatus(paperId)
        if (s.status === "processing") {
          setPastPapersUser(prev =>
            prev.map(p => p.id !== paperId ? p : { ...p, processingPhase: s.processing_phase })
          )
        } else {
          clearInterval(interval)
          pollingMap.current.delete(paperId)
          notify({
            header: "Past paper processed",
            content: "Your past paper has been processed and is ready to solve!",
            button: {
              buttonText: "Go to past papers",
              onButtonClick: () => router.push(`/folders/${folderId}?tab=past-papers`)
            }
          })
          setPastPapersUser(prev =>
            prev.map(p => p.id !== paperId ? p : {
              ...p,
              status: s.status as PastPaperUserInfo["status"],
              paperFailureStatus: s.status === "failed" ? p.paperFailureStatus ?? null : null,
              processingPhase: null,
            })
          )
        }
      } catch {
        clearInterval(interval)
        pollingMap.current.delete(paperId)
      }
    }, 3000)
    pollingMap.current.set(paperId, interval)
  }, [folderId, router])

  const getFailureStatus = useCallback((error: unknown): number | null => {
    return getHttpStatus(error)
  }, [])

  // Re-fetch the list and merge in any newly-appeared papers without clearing
  // existing state — used when a background upload confirms via "started" event
  // after this component has remounted from navigation.
  const forceRefreshRef = useRef<() => void>(null!)
  const forceRefresh = useCallback(() => {
    listPastPapersApiV1PastPapersGet({ folder_id: folderId }, { cache: "no-store" }).then((resp) => {
      if (resp.status !== 200 || !Array.isArray(resp.data)) return
      const fetched = resp.data.map((paper: PastPaperListOut & { processing_phase?: string | null }) => ({
        id: paper.id,
        title: paper.name,
        status: paper.status as PastPaperUserInfo["status"],
        paperFailureStatus: null,
        markFailureStatus: null,
        processingPhase: (paper.processing_phase as PastPaperUserInfo["processingPhase"] | null | undefined) ?? null,
        markState: paper.mark_scheme_filename
          ? { status: "completed" as const, name: paper.mark_scheme_filename }
          : { status: "none" as const }
      }))
      setPastPapersUser(prev => {
        const prevIds = new Set(prev.map(p => p.id))
        const added = fetched.filter(p => !prevIds.has(p.id))
        return added.length ? [...prev, ...added] : prev
      })
      fetched.filter(p => p.status === "processing").forEach(p => pollPaperStatus(p.id))
    }).catch(e => console.error("Failed to refresh past papers:", e))
  }, [folderId, pollPaperStatus])
  forceRefreshRef.current = forceRefresh

  // Clear polling intervals on unmount to prevent network-request leaks.
  useEffect(() => {
    return () => {
      isMountedRef.current = false
      pollingMap.current.forEach(clearInterval)
      pollingMap.current.clear()
    }
  }, [])

  // Register this provider in the module-level store so that a background
  // uploadPaper (from a previous mount) can trigger a re-fetch after navigation.
  useEffect(() => {
    const refresh = () => forceRefreshRef.current()
    _folderRefreshFns.set(folderId, refresh)
    if (_pendingRefreshFolders.has(folderId)) {
      _pendingRefreshFolders.delete(folderId)
      refresh()
    }
    return () => { _folderRefreshFns.delete(folderId) }
  }, [folderId])

  const attachMark = useCallback(
    (paperId: string, file?: File) => {
      const info = paperUploadList.current.get(paperId)
      const fileToUpload = file ?? info?.markFile
      const actualId = info?.newId ?? paperId
      const paper = pastPapersUser.find(paper => paper.id === actualId)
      if (info?.newId)
        paperUploadList.current.delete(paperId)
      if (!paper)
        throw Error(`Failed to find paper with id ${actualId}`)
      if (!fileToUpload)
        throw Error(`Failed to find file to upload for ${actualId}`)

      if (file)
        paperUploadList.current.set(actualId, { markFile: file })

      if (paper.status !== "ready") {
        setPastPapersUser(prev =>
          prev.map(paper => paper.id !== actualId
            ? paper
            : { ...paper, markState: { status: "waiting" } }
          )
        )
        return
      }

      setPastPapersUser(prev =>
        prev.map(paper => paper.id !== actualId
          ? paper
          : { ...paper, markState: { status: "processing" }, markFailureStatus: null }
        )
      )

      uploadMarkSchemeApiV1PastPapersPastPaperIdMarkSchemePost(actualId, { file: fileToUpload }).then(resp => {
        setPastPapersUser(prev =>
          prev.map(paper => paper.id !== actualId
            ? paper
            : {
              ...paper,
              markFailureStatus: null,
              markState: resp.status === 200
                ? { status: "completed", name: resp.data.mark_scheme_filename ?? fileToUpload.name }
                : { status: "failed" }
            }
          )
        )
        paperUploadList.current.delete(actualId)
      }).catch(e => {
        console.error(e)
        setPastPapersUser(prev =>
          prev.map(paper => paper.id !== actualId
            ? paper
            : {
              ...paper,
              markState: { status: "failed" },
              markFailureStatus: getFailureStatus(e),
            }
          )
        )
      })
    },
    [getFailureStatus, pastPapersUser]
  )

  const removeMark = useCallback(
    (paperId: string) => {
      if (pastPapersUser.find(paper => paper.id === paperId)?.markState.status !== "completed") {
        setPastPapersUser(prev =>
          prev.map(paper => paper.id !== paperId
            ? paper
            : { ...paper, markState: { status: "none" }, markFailureStatus: null }
          )
        )
        paperUploadList.current.delete(paperId)
        return
      }

      setPastPapersUser(prev =>
        prev.map(paper => paper.id !== paperId
          ? paper
          : { ...paper, markState: { status: "none" }, markFailureStatus: null }
        )
      )
      paperUploadList.current.delete(paperId)

      deleteMarkSchemeApiV1PastPapersPastPaperIdMarkSchemeDelete(paperId)
    },
    [pastPapersUser]
  )

  const uploadPaper = useCallback(
    async (paperId: string) => {
      const info = paperUploadList.current.get(paperId)
      if (!info || !info.paperFile) return

      setPastPapersUser(prev =>
        prev.map(paper => paper.id !== paperId
          ? paper
          : {
            ...paper,
            status: "processing",
            paperFailureStatus: null,
            markState: { status: info.markFile ? "waiting" : "none" }
          }
        )
      )

      // Track the real paper id assigned by the backend (received in the "started" event).
      // Falls back to the temp paperId if the SSE closes before "started" arrives.
      let realPaperId = paperId
      let terminated = false  // set to true when "complete" or "error" is received

      try {
        let markFailed = false

        const generator = streamPastPaperUpload({
          file: info.paperFile,
          name: info.paperFile.name,
          folder_id: folderId,
          mark_scheme_file: info.markFile
        });

        for await (const event of generator) {
          switch (event.event) {
            case "started":
              // real paper_id is available — swap temp id for real one early
              realPaperId = event.paper_id
              if (event.paper_id !== paperId) {
                setPastPapersUser(prev =>
                  prev.map(p => p.id !== paperId ? p : { ...p, id: event.paper_id })
                )
                const info = paperUploadList.current.get(paperId)
                if (info) {
                  paperUploadList.current.set(event.paper_id, info)
                  paperUploadList.current.delete(paperId)
                }
                // The paper is now committed to the DB. If the user navigated away
                // while the file was uploading, trigger a re-fetch in the currently
                // active provider so the paper reappears without manual refresh.
                if (!isMountedRef.current) {
                  _triggerFolderRefresh(folderId)
                }
              }
              break;
            case "processing":
              setPastPapersUser(prev =>
                prev.map(paper => paper.id !== realPaperId
                  ? paper
                  : {
                    ...paper,
                    processingPhase: event.phase,
                    ...(event.phase === "mark_scheme_parsing"
                      ? { markState: { status: "processing" as const } }
                      : {})
                  }
                )
              )
              break;
            case "mark_scheme_failed":
            case "mark_scheme_unassigned":
              markFailed = true
              setPastPapersUser(prev =>
                prev.map(paper => paper.id !== realPaperId
                  ? paper
                  : { ...paper, markState: { status: "failed" }, markFailureStatus: null }
                )
              )
              break;

            // "error" is not an SSE event — handled in the catch block below

            case "complete":
              terminated = true
              setPastPapersUser(prev =>
                prev.map(paper => paper.id !== realPaperId
                  ? paper
                  : {
                    id: event.paper_id,
                    title: event.name,
                    status: "ready",
                    paperFailureStatus: null,
                    markState: info.markFile && !markFailed
                      ? { name: info.markFile.name, status: "completed" }
                      : paper.markState
                  }
                )
              )
              notify({
                header: "Past paper processed",
                content: "Your past paper has been processed and is ready to solve!",
                button: {
                  buttonText: "Go to past papers",
                  onButtonClick: () => router.push(`/folders/${folderId}?tab=past-papers`)
                }
              })

              const freshInfo = paperUploadList.current.get(realPaperId)
              if (freshInfo?.attachingMarkFile) {
                paperUploadList.current.set(realPaperId, { newId: event.paper_id })
              } else {
                paperUploadList.current.delete(realPaperId)
              }

              // add mark file info for retry upload if failed
              if (markFailed)
                paperUploadList.current.set(event.paper_id, { markFile: freshInfo!.markFile })


              // only attach mark separately if it was added AFTER the upload started
              // (not if it was already included in the upload FormData)
              if (freshInfo?.attachingMarkFile && freshInfo?.markFile)
                attachMarkAfterUpload.current = { id: event.paper_id, file: freshInfo.markFile }
              break;
          }
        }
      } catch (err) {
        console.error(err)
        setPastPapersUser(prev =>
          prev.map(paper => paper.id !== paperId
            ? paper
            : {
              ...paper,
              status: "failed",
              processingPhase: null,
              paperFailureStatus: getFailureStatus(err)
            }
          )
        )
      }

      // If the SSE stream closed before we received a terminal event (complete/error),
      // the backend task is still running. Switch to polling so the UI stays in sync.
      // Only poll if realPaperId was updated from the backend "started" event —
      // if it's still the temp client-side NanoID, the stream died before processing
      // began and there's nothing on the server to poll.
      if (!terminated && realPaperId !== paperId) {
        if (isMountedRef.current) {
          pollPaperStatus(realPaperId)
        } else {
          _triggerFolderRefresh(folderId)
        }
      }
    },
    [router, folderId, getFailureStatus, pollPaperStatus]
  )

  useEffect(() => {
    if (!attachMarkAfterUpload.current) return

    attachMark(attachMarkAfterUpload.current.id, attachMarkAfterUpload.current.file)
    attachMarkAfterUpload.current = null
  }, [pastPapersUser, attachMark])

  const removePaper = useCallback(
    (paperId: string) => {
      setPastPapersUser(prev => prev.filter(paper => paper.id !== paperId))
      paperUploadList.current.delete(paperId)
      deletePastPaperApiV1PastPapersPastPaperIdDelete(paperId)
    },
    []
  )

  const addPapersToUpload = useCallback(
    (...papers: UploadInfo[]) => {
      const newPapers = papers.filter(p => p.paper !== undefined)

      newPapers.forEach(p => {
        paperUploadList.current.set(p.id, {
          paperFile: p.paper,
          markFile: p.mark
        })
      })

      setPastPapersUser(prev => [
        ...prev,
        ...newPapers.map<PastPaperUserInfo>(p => ({
          id: p.id,
          title: p.paper!.name,
          status: "processing",
          paperFailureStatus: null,
          markFailureStatus: null,
          markState: { status: p.mark ? "waiting" : "none" }
        }))
      ])

      newPapers.forEach(p => uploadPaper(p.id))
    },
    [uploadPaper]
  )

  const attachingMark = useCallback(
    (paperId: string) => {
      const paper = paperUploadList.current.get(paperId)
      if (paper)
        paperUploadList.current.set(paperId, { ...paper, attachingMarkFile: true })
    },
    []
  )

  const removeAttachingMark = useCallback(
    (paperId: string) => {
      paperUploadList.current.delete(paperId)
    },
    []
  )

  const renamePaper = useCallback(
    (paperId: string, title: string) => {
      setPastPapersUser(prev =>
        prev.map(paper => paper.id !== paperId
          ? paper
          : { ...paper, title }
        )
      )

      const body = new URLSearchParams({ name: title })
      fetch(`/api/v1/past-papers/${encodeURIComponent(paperId)}/rename`, {
        method: "PATCH",
        body,
      }).catch(e => console.error("Failed to rename past paper:", e))
    },
    []
  )

  useEffect(() => {
    let cancelled = false
    paperUploadList.current.clear()
    attachMarkAfterUpload.current = null
    setPastPapersUser([])
    setPastPapersNova([])
    setLoading(true)
    listPastPapersApiV1PastPapersGet({ folder_id: folderId }, { cache: "no-store" }).then((resp) => {
      if (cancelled || resp.status !== 200 || !Array.isArray(resp.data)) return

      const papers = resp.data.map((paper: PastPaperListOut & { processing_phase?: string | null }) => ({
        id: paper.id,
        title: paper.name,
        status: paper.status as PastPaperUserInfo["status"],
        paperFailureStatus: null,
        markFailureStatus: null,
        processingPhase: (paper.processing_phase as PastPaperUserInfo["processingPhase"] | null | undefined) ?? null,
        markState: paper.mark_scheme_filename
          ? { status: "completed" as const, name: paper.mark_scheme_filename }
          : { status: "none" as const }
      }))
      setPastPapersUser(papers)

      // resume polling for any papers still processing
      papers
        .filter(p => p.status === "processing")
        .forEach(p => pollPaperStatus(p.id))
    }).catch(e => {
      if (!cancelled) console.error("Failed to load past papers:", e)
    }).finally(() => {
      if (!cancelled) setLoading(false)
    });
    return () => { cancelled = true }
  }, [folderId, pollPaperStatus])

  const value: PastPapersContextValue = {
    pastPapersUser,
    pastPapersNova,
    loading,
    uploadPaper,
    attachMark,
    removeMark,
    removePaper,
    attachingMark,
    removeAttachingMark,
    addPapersToUpload,
    renamePaper
  };

  return (
    <PastPapersContext.Provider value={value}>{children}</PastPapersContext.Provider>
  );
}

export function usePastPapers(): PastPapersContextValue {
  const ctx = useContext(PastPapersContext)
  if (!ctx) throw new Error("usePastPapers must be used within PastPapersProvider")
  return ctx
}
