import { Button, cn } from "@/shared";
import { CheckedIcon, EditIcon, FileSearchIcon, FileVerifiedIcon, MarkLoaderIcon, PastPaperCardIcon, InfoCircleIcon, RetryIcon, TrashIcon, XMarkIcon } from "@/shared/assets/icons";
import { MarkState, usePastPapers } from "../../model/past-papers-context";
import { useState, useEffect, useRef, useCallback } from "react";
import { getUploadErrorMessage } from "@/shared/api/http-error-message";

const bottomTextClass = "flex-1 nova-text-label-small-regular"

type PaperCardProps = {
    id: string
    title: string
    percent?: number
    status: "processing" | "ready" | "failed"
    paperFailureStatus?: number | null
    markFailureStatus?: number | null
    onPastPaperSelect(id: string): void,
    isSelected?: boolean
    isSmall?: boolean
} & ({
    isNova: true,
    markState?: never,
    status: "ready"
    onAttachMark?: never
} | {
    isNova?: never,
    markState: MarkState,
    processingPhase?: "ocr" | "mark_scheme_parsing" | "parsing" | "mark_scheme_matching" | "matching" | null
    onAttachMark(id: string): void
})

const PHASE_RANGE_WITH_MARK: Record<string, [number, number]> = {
    ocr:                  [6,  12],
    mark_scheme_parsing:  [16, 23],
    parsing:              [28, 38],
    mark_scheme_matching: [72, 80],
    matching:             [84, 91],
}

const PHASE_RANGE_NO_MARK: Record<string, [number, number]> = {
    ocr:     [8,  15],
    parsing: [25, 35],
    matching:[82, 90],
}

function seededRandom(seed: string): number {
    let h = 0
    for (let i = 0; i < seed.length; i++) {
        h = Math.imul(31, h) + seed.charCodeAt(i) | 0
    }
    return (h >>> 0) / 0xFFFFFFFF
}

function getProcessingPercent(paperId: string, phase?: string | null, hasMarkScheme?: boolean): number {
    if (!phase) return 3
    const table = hasMarkScheme ? PHASE_RANGE_WITH_MARK : PHASE_RANGE_NO_MARK
    const range = table[phase]
    if (!range) return 3
    const [min, max] = range
    return Math.round(min + seededRandom(paperId + phase) * (max - min))
}

const TRICKLE: Record<string, { ratePerSec: number; maxDelta: number }> = {
    ocr:                  { ratePerSec: 0.6, maxDelta: 13 },
    parsing:              { ratePerSec: 0.9, maxDelta: 50 },
    mark_scheme_parsing:  { ratePerSec: 0.6, maxDelta: 10 },
    mark_scheme_matching: { ratePerSec: 0.7, maxDelta:  8 },
    matching:             { ratePerSec: 0.8, maxDelta:  7 },
}

function useProcessingPercent(
    paperId: string,
    phase: string | null | undefined,
    hasMarkScheme: boolean,
    status: string,
): number {
    const storageKey = `pp-pct-${paperId}`

    const target = status === "processing"
        ? getProcessingPercent(paperId, phase, hasMarkScheme)
        : 0

    const [initialPct] = useState<number>(() => {
        if (typeof window === "undefined" || status !== "processing") return 0
        const saved = localStorage.getItem(`pp-pct-${paperId}`)
        return saved ? Math.min(99, Math.max(0, Number(saved))) : 0
    })

    const valRef  = useRef(initialPct)
    const [display, setDisplay] = useState(initialPct)
    const rafRef  = useRef<number>(0)
    const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)

    const save = useCallback((v: number) => {
        localStorage.setItem(storageKey, String(Math.round(v)))
    }, [storageKey])

    useEffect(() => {
        cancelAnimationFrame(rafRef.current)
        if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null }

        if (status !== "processing") {
            localStorage.removeItem(storageKey)
            valRef.current = 0
            queueMicrotask(() => {
                setDisplay(0)
            })
            return
        }

        const from = valRef.current
        const cfg = phase ? TRICKLE[phase] : null
        const HARD_CAP = 99

        if (target <= from) {
            if (!cfg) return
            const ceiling = Math.min(HARD_CAP, from + cfg.maxDelta)
            tickRef.current = setInterval(() => {
                if (valRef.current >= ceiling) {
                    clearInterval(tickRef.current!); tickRef.current = null; return
                }
                valRef.current = Math.min(ceiling, valRef.current + cfg.ratePerSec)
                save(valRef.current)
                setDisplay(Math.round(valRef.current))
            }, 1000)
            return () => { if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null } }
        }

        const t0 = performance.now()
        const clampedTarget = Math.min(HARD_CAP, target)
        const animate = (now: number) => {
            const p = Math.min((now - t0) / 800, 1)
            const eased = 1 - (1 - p) ** 2
            valRef.current = Math.min(HARD_CAP, from + (clampedTarget - from) * eased)
            save(valRef.current)
            setDisplay(Math.round(valRef.current))
            if (p < 1) { rafRef.current = requestAnimationFrame(animate); return }

            if (!cfg) return
            const ceiling = Math.min(HARD_CAP, clampedTarget + cfg.maxDelta)
            tickRef.current = setInterval(() => {
                if (valRef.current >= ceiling) {
                    clearInterval(tickRef.current!); tickRef.current = null; return
                }
                valRef.current = Math.min(ceiling, valRef.current + cfg.ratePerSec)
                save(valRef.current)
                setDisplay(Math.round(valRef.current))
            }, 1000)
        }
        rafRef.current = requestAnimationFrame(animate)

        return () => {
            cancelAnimationFrame(rafRef.current)
            if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null }
        }
    }, [target, status, storageKey, phase, save])

    return display
}

export function PaperCard(props: PaperCardProps) {
    const { id, title, percent, markState, status, paperFailureStatus, markFailureStatus, isNova, isSelected, isSmall, onPastPaperSelect, onAttachMark } = props
    const processingPhase = (props as Extract<PaperCardProps, { isNova?: never }>).processingPhase
    const { attachMark, removeMark, uploadPaper, removePaper, renamePaper } = usePastPapers()

    const [isEditing, setIsEditing] = useState(false)
    const [newName, setNewName] = useState("")

    const animatedPercent = useProcessingPercent(id, processingPhase, markState?.status !== "none", status)

    return (
        <div
            className={cn("group relative flex flex-col max-w-90 min-h-24 max-h-60 border border-[#F4F2F1] hover:border-[#E4DFDD] rounded-[16px] transition-shadow hover:nova-shadow-triple cursor-pointer select-none", isSelected && "selected nova-shadow-triple border-[#E4DFDD] bg-[#FAF8F7]")}
            onClick={() => {
                if (status !== "ready" || isEditing || getSelection()?.toString().length !== 0) return
                onPastPaperSelect(id)
            }}
        >
            {status !== "failed" &&
                <div className="flex gap-x-1 z-10 absolute top-2 right-2 invisible group-hover:visible">
                    {status !== "processing" &&
                        <Button
                            iconOnly
                            variant="plain"
                            size="xxs"
                            className="flex shrink-0 items-center justify-center transition-all opacity-50 hover:opacity-100"
                            onClick={e => {
                                e.stopPropagation()
                                if (isEditing) {
                                    renamePaper(id, newName)
                                    setIsEditing(false)
                                } else {
                                    setNewName(title)
                                    setIsEditing(true)
                                }
                            }}
                        >
                            {isEditing
                                ? <CheckedIcon className="size-4" />
                                : <EditIcon className="size-4" />
                            }
                        </Button>
                    }
                    <Button
                        iconOnly
                        variant="plain"
                        size="xxs"
                        className="flex shrink-0 items-center justify-center transition-all opacity-50 hover:opacity-100"
                        onClick={e => {
                            e.stopPropagation()
                            if (isEditing) {
                                setIsEditing(false)
                            } else {
                                removePaper(id)
                            }
                        }}
                    >
                        {isEditing
                            ? <XMarkIcon className="size-4" />
                            : <TrashIcon className="size-4" />
                        }
                    </Button>
                </div>
            }

            {status === "failed" ? (
                <div className="flex flex-col justify-center items-center py-3">
                    <InfoCircleIcon className="size-5 text-[#DB7D3C]" />
                    <p className="mt-1 nova-text-label-small-regular text-[#DB7D3C]">Upload unsuccessful</p>
                    <p className="mt-1 px-3 text-center nova-text-label-small-regular text-[#A1A1AA]">
                        {getUploadErrorMessage(paperFailureStatus ?? null, "paper")}
                    </p>
                    <div className="mt-2.5 flex gap-x-1.5">
                        <Button
                            size="xs"
                            variant="outline"
                            onClick={e => {
                                e.stopPropagation()
                                removePaper(id)
                            }}
                        >
                            Remove
                        </Button>
                        <Button
                            size="xs"
                            variant="outline"
                            onClick={e => {
                                e.stopPropagation()
                                uploadPaper(id)
                            }}
                        >
                            Retry
                        </Button>
                    </div>
                </div>
            ) : (
                <div className="flex gap-x-6 py-1.5 pl-1.5 pr-6">
                    <div className={cn("shrink-0", status === "processing" && "animate-icon-pulse")}>
                        <PastPaperCardIcon className="shrink-0 **:transition-colors" />
                    </div>

                    <div className="flex-1 flex flex-col justify-center min-w-0">
                        {isEditing ? (
                            <input
                                type="text"
                                value={newName}
                                onChange={e => setNewName(e.target.value)}
                                className="nova-text-label-small text-[#232120] outline-none"
                            />
                        ) : (
                            <p className="max-w-full nova-text-label-small text-[#232120] whitespace-nowrap overflow-x-hidden text-ellipsis">{status === "processing" ? "Past paper is being processed..." : title}</p>
                        )}

                        {status === "processing" ? (
                            <>
                                <div className="mt-2.5 w-16 h-2 bg-[#E4E4E7] rounded-full animate-icon-pulse" />
                                <p className="mt-1.5 nova-text-label-small-regular text-[#A1A1AA]">{animatedPercent}%</p>
                            </>
                        ) : (
                            <>
                                <p className="mt-1 nova-text-label-small-regular text-[#A1A1AA]">best attempt: {percent ?? 0}%</p>

                                <div className="mt-3 w-full h-1 rounded-full bg-[#F7F4F2]">
                                    <div
                                        className="h-full rounded-full bg-[#D3CCC8]"
                                        style={{
                                            width: (percent ?? 0) + "%"
                                        }}
                                    />
                                </div>
                            </>
                        )}

                    </div>
                </div>
            )}
            {!isSmall &&
                <div className="flex-1 flex gap-x-1.5 items-center p-2 border-t border-[#F4F2F1] group-hover:border-[#E4DFDD]">
                    {isNova ? (
                        <>
                            <FileVerifiedIcon className="text-[#A1A1AA]" />
                            <p className={cn(bottomTextClass, "text-[#A1A1AA]")}>Mark scheme attached</p>
                        </>
                    ) : markState.status === "waiting" ? (
                        <>
                            <MarkLoaderIcon className="animate-spin" />
                            <p className={cn(bottomTextClass, "text-[#A1A1AA]")}>Mark scheme is waiting to be processed...</p>
                        </>
                    ) : markState.status === "processing" ? (
                        <>
                            <MarkLoaderIcon className="animate-spin" />
                            <p className={cn(bottomTextClass, "text-[#A1A1AA]")}>Mark scheme is being processed...</p>
                        </>
                    ) : markState.status === "failed" ? (
                        <>
                            <div className="flex justify-center items-center size-6 rounded-full nova-shadow-sm">
                                <InfoCircleIcon className="size-4 text-[#DB7D3C]" />
                            </div>
                            <p className={cn(bottomTextClass, "text-[#DB7D3C]")}>
                                {markFailureStatus !== null && markFailureStatus !== undefined
                                    ? getUploadErrorMessage(markFailureStatus, "mark_scheme")
                                    : "The mark scheme was not suitable or was not found"}
                            </p>
                            {!isEditing &&
                                <>
                                    <Button
                                        iconOnly
                                        variant="plain"
                                        size="xs"
                                        onClick={e => {
                                            e.stopPropagation()
                                            attachMark(id)
                                        }}
                                    >
                                        <RetryIcon className="size-4" />
                                    </Button>
                                    <Button
                                        size="xs"
                                        variant="outline"
                                        onClick={e => {
                                            e.stopPropagation()
                                            removeMark(id)
                                        }}
                                    >
                                        Remove
                                    </Button>
                                </>
                            }
                        </>
                    ) : markState.status === "completed" ? (
                        <>
                            <FileVerifiedIcon className="text-[#242529]" />
                            <p className={cn(bottomTextClass, "text-[#242529]")}>{markState.name}</p>
                            {!isEditing &&
                                <Button
                                    size="xs"
                                    variant="outline"
                                    onClick={e => {
                                        e.stopPropagation()
                                        removeMark(id)
                                    }}
                                >
                                    Remove
                                </Button>
                            }
                        </>
                    ) : (
                        <>
                            <FileSearchIcon />
                            <p className={cn(bottomTextClass, "text-[#A1A1AA]")}>Mark scheme is not attached to the file</p>
                            {!isEditing &&
                                <Button
                                    size="xs"
                                    variant="outline"
                                    onClick={e => {
                                        e.stopPropagation()
                                        onAttachMark(id)
                                    }}
                                >
                                    Attach
                                </Button>
                            }
                        </>
                    )}
                </div>
            }
        </div>
    )
}