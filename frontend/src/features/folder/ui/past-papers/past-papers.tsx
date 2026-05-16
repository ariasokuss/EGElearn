import { FileUploadIcon, LoaderIcon } from "@/shared/assets/icons";
import { PaperCard } from "./past-papers-card";
import { usePastPapers } from "../../model/use-past-papers";
import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { TestSessionOut } from "@/shared/api/generated/model";
import { TestHistoryPanel } from "@/shared/ui/test-history-panel/test-history-panel";
import { useTests } from "@/features/practice-questions/model";
import { Modal } from "@/shared/ui";
import { cn } from "@/shared";
import { readFolderUi, writeFolderUi } from "../../lib/lesson-ui-state";

type PastPapersProps = {
    onPastPaperUploadClick(): void
    onPastPaperSelect(id: string): void
    isMultiPanel: boolean,
    selectedPastPaperId: string
    folderId: string
    onOpenTestResult(session: TestSessionOut): void
    onResumeTest(session: TestSessionOut): void
    pastPaperSessionsRefreshRef?: MutableRefObject<(() => void) | null>
}

function toPercent(score: number): number {
    if (Number.isNaN(score)) return 0;
    if (score <= 0) return 0;
    if (score <= 1) return Math.round(score * 100);
    return Math.round(Math.min(score, 100));
}

function sessionPercent(session: TestSessionOut): number {
    if (typeof session.score === "number") {
        return toPercent(session.score);
    }
    if (typeof session.earned_marks === "number" && session.total_marks > 0) {
        return toPercent(session.earned_marks / session.total_marks);
    }
    return 0;
}

export function PastPapers({ onPastPaperUploadClick, onPastPaperSelect, isMultiPanel, selectedPastPaperId, onOpenTestResult, onResumeTest, folderId, pastPaperSessionsRefreshRef }: PastPapersProps) {
    const { pastPapersUser, pastPapersNova, loading, attachMark, removeAttachingMark, attachingMark } = usePastPapers()

    const {
        sessions,
        sessionsLoading,
        loadSessions,
    } = useTests(folderId, "past_paper");

    useEffect(() => {
        if (!pastPaperSessionsRefreshRef) return
        const ref = pastPaperSessionsRefreshRef
        const refresh = () => { void loadSessions() }
        ref.current = refresh
        return () => {
            if (ref.current === refresh) ref.current = null
        }
    }, [loadSessions, pastPaperSessionsRefreshRef])

    const [activeGroup, setActiveGroup] = useState(readFolderUi(folderId)?.pastPaperTestHistoryTab ?? "")
    const handleActiveGroupChange = (group: string) => {
        writeFolderUi(folderId, {pastPaperTestHistoryTab: group})
        setActiveGroup(group)
    }

    const [isModalOpen, setIsModalOpen] = useState(false)
    const freshSession = useRef<TestSessionOut | undefined>(undefined)

    const fileInputRef = useRef<HTMLInputElement>(null)
    const attachingPaperId = useRef("")
    const onMarkFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files
        if (!files) return

        attachMark(attachingPaperId.current, files[0])
        attachingPaperId.current = ""
    }
    const onMarkFileCancel = () => {
        if (attachingPaperId.current)
            removeAttachingMark(attachingPaperId.current)
    }
    const onAttachMark = (id: string) => {
        if (!fileInputRef.current) return
        attachingPaperId.current = id
        attachingMark(id)
        fileInputRef.current.click()
    }

    const bestAttemptByPaperId = sessions.reduce<Record<string, number>>((acc, session) => {
        const templateId = session.template_id;
        const percent = sessionPercent(session);
        acc[templateId] = Math.max(acc[templateId] ?? 0, percent);
        return acc;
    }, {});

    if (loading || sessionsLoading) {
        return (
            <div className="flex items-center justify-center py-16">
                <LoaderIcon className="animate-spin" />
            </div>
        )
    }

    const closeModal = () => setIsModalOpen(false)
    const handleNewAttempt = () => {
        if (!freshSession.current) return
        onPastPaperSelect(freshSession.current.template_id)
        setIsModalOpen(false)
    }
    const handlePreviousAttempt = () => {
        if (!freshSession.current) return
        onResumeTest(freshSession.current)
        setIsModalOpen(false)
    }

    const handlePastPaperSelect = (id: string) => {
        freshSession.current = sessions.reduce<TestSessionOut | undefined>((fresh, session) => {
            if (
                session.template_id !== id ||
                session.status !== "not_started" && session.status !== "active"
            ) return fresh
            if (!fresh) return session
            return fresh.updated_at > session.updated_at ? fresh : session
        }, undefined)
        if (freshSession.current) {
            setIsModalOpen(true)
            return
        }
        onPastPaperSelect(id)
    }

    const testOpen = !!selectedPastPaperId
    const onSelectResult = (session: TestSessionOut) => {
        if (session.status === "not_started" || session.status === "active")
            onResumeTest(session)
        else
            onOpenTestResult(session)
    }

    return (
        <div
            className={cn("flex", !isMultiPanel && "duration-300 ease-in-out transition-[padding-right]")}
            style={{ paddingRight: isMultiPanel ? 0 : activeGroup ? "clamp(300px, 25vw, 400px)" : 165 }}
        >
            <Modal
                isOpen={isModalOpen}
                title="Do you want to start a new attempt or continue the previous one?"
                primaryButtonText="New attempt"
                secondaryButtonText="Previous attempt"
                onPrimaryClick={handleNewAttempt}
                onSecondaryClick={handlePreviousAttempt}
                onXClick={closeModal}
            />

            <div className="flex-1 flex flex-col gap-y-6 pt-7 **:transition-colors">
                <div className="flex flex-col gap-y-4">
                    <p className="nova-text-label-base text-[#1D1B20]">Nova past papers</p>
                    <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,360px))] gap-3">
                        {pastPapersNova.length === 0 ? (
                            <p className="nova-text-p-base text-[#A1A1AA]">Coming soon...</p>
                        ) : (
                            pastPapersNova.map(paper =>
                                <PaperCard
                                    key={paper.id}
                                    isNova
                                    onPastPaperSelect={handlePastPaperSelect}
                                    isSelected={paper.id === selectedPastPaperId}
                                    isSmall={testOpen}
                                    {...paper}
                                    percent={bestAttemptByPaperId[paper.id] ?? 0}
                                />
                            )
                        )}
                    </div>
                </div>

                <div className="flex flex-col gap-y-4">
                    <p className="nova-text-label-base text-[#1D1B20]">My past papers</p>
                    <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,360px))] gap-3">
                        {!isMultiPanel &&
                            <button
                                className="flex items-center justify-center gap-x-1 min-h-24 max-h-60 max-w-90 border border-[#F4F2F1] rounded-[16px] transition-shadow nova-text-label-small text-[#242529] active:bg-[#FAF8F7] hover:nova-shadow-triple hover:border-[#E3DEDB]"
                                onClick={onPastPaperUploadClick}
                            >
                                <FileUploadIcon />
                                Upload past paper
                            </button>
                        }

                        <input
                            ref={node => {
                                fileInputRef.current = node
                                if (node)
                                    node.oncancel = onMarkFileCancel
                            }}
                            type="file"
                            accept={".pdf"}
                            onClick={e => e.stopPropagation()}
                            onChange={onMarkFileSelect}
                            hidden
                        />

                        {pastPapersUser.map(paper =>
                            <PaperCard
                                key={paper.id}
                                onPastPaperSelect={onPastPaperSelect}
                                onAttachMark={onAttachMark}
                                isSelected={paper.id === selectedPastPaperId}
                                isSmall={testOpen}
                                {...paper}
                                percent={bestAttemptByPaperId[paper.id] ?? 0}
                            />
                        )}
                    </div>
                </div>
            </div>

            {!isMultiPanel &&
                <TestHistoryPanel
                    loading={sessionsLoading}
                    onSelect={onSelectResult}
                    sessions={sessions}
                    activeGroup={activeGroup}
                    setActiveGroup={handleActiveGroupChange}
                    tab="past-papers"
                />
            }
        </div>
    )
}
