import { ChatInput, ChatMessages } from "@/features/chat";
import { useFeynmanChat } from "@/features/folder/model/use-feynman-chat";
import { abortSessionApiV1FeynmanSessionSessionIdAbortPost } from "@/shared/api";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Modal } from "@/shared/ui";
import { ModalProps } from "@/shared/ui/modal/modal";
import { LoaderIcon } from "@/shared/assets/icons";

type ExplanationChatProps = {
    lessonId: string,
    navigateResults(id: string): void,
    historySessionId?: string
    resumeInitialSessionId?: string
    onPersistFeynmanSession?: (sessionId: string | null) => void
}

export function ExplanationChat({
    lessonId,
    historySessionId,
    resumeInitialSessionId,
    onPersistFeynmanSession,
    navigateResults,
}: ExplanationChatProps) {
    const initialSessionId = historySessionId ?? resumeInitialSessionId
    const {
        sessionId,
        messages,
        status,
        isCompleted,
        error,
        reload,
        input,
        setInput,
        taggedPart,
        setTaggedPart,
        handleSubmit,
    } = useFeynmanChat({ lessonId, sessionId: initialSessionId })

    const [isModalOpen, setIsModalOpen] = useState(false)

    const [resultsLoading, setResultsLoading] = useState(false)
    const hasAutoStoppedRef = useRef(false)
    const isMountedRef = useRef(true)
    const [isAtBottom, setIsAtBottom] = useState(true)
    const scrollToBottomRef = useRef<VoidFunction>(() => { })
    const scrollToLastUserRef = useRef<VoidFunction>(() => { })

    const handleScrollStateChange = useCallback((atBottom: boolean, scrollFn: VoidFunction, _scrollAssistant: VoidFunction, scrollUser: VoidFunction) => {
        setIsAtBottom(atBottom)
        scrollToBottomRef.current = scrollFn
        scrollToLastUserRef.current = scrollUser
    }, [])

    const handleSend = useCallback(() => {
        handleSubmit()
        requestAnimationFrame(() => {
            const spacer = document.querySelector<HTMLElement>("[data-chat-spacer]");
            if (spacer) spacer.style.minHeight = "60vh";
            requestAnimationFrame(() => {
                scrollToLastUserRef.current();
            });
        });
    }, [handleSubmit])

    const stopSession = useCallback(async (exhausted: boolean, navigate = true) => {
        if (!sessionId) return
        if (isMountedRef.current) {
            setResultsLoading(true)
        }
        try {
            const resp = await abortSessionApiV1FeynmanSessionSessionIdAbortPost(sessionId, { exhausted })
            if (resp.status !== 200 || !navigate) return
            navigateResults(resp.data.id)
        } catch (err) {
            console.error("Failed to stop Feynman session", err)
        } finally {
            if (isMountedRef.current) {
                setResultsLoading(false)
            }
        }
    }, [sessionId, navigateResults])

    useEffect(() => {
        isMountedRef.current = true
        return () => {
            isMountedRef.current = false
        }
    }, [])

    useEffect(() => {
        hasAutoStoppedRef.current = false
    }, [sessionId])

    useEffect(() => {
        if (historySessionId) return
        if (sessionId) {
            onPersistFeynmanSession?.(sessionId)
        }
    }, [sessionId, historySessionId, onPersistFeynmanSession])

    useEffect(() => {
        if (!isCompleted || !sessionId || hasAutoStoppedRef.current) return
        hasAutoStoppedRef.current = true
        void stopSession(false)
    }, [isCompleted, sessionId, stopSession])

    if (resultsLoading) {
        return (
            <div className="flex items-center justify-center py-16">
                <LoaderIcon className="animate-spin" />
            </div>
        )
    }

    const modalProps: ModalProps = {
        isOpen: isModalOpen,
        onXClick: () => setIsModalOpen(false),
        onPrimaryClick: () => {
            void stopSession(true)
        },
        onSecondaryClick: () => {
            void stopSession(false)
        },
        primaryButtonText: "I wrote everything I know",
        secondaryButtonText: "I just want to quit",
        title: "Are you sure you want to end the session?",
        description: "Your grade will only take into account what you already wrote.",
    }


    return (
        <div className="flex w-full h-full">
            <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
                <div className="absolute inset-0 flex flex-col">
                    <ChatMessages
                        messages={messages}
                        status={status}
                        onScrollStateChange={handleScrollStateChange}
                        onSetTaggedPart={
                            !historySessionId
                                ? (part) => {
                                    setTaggedPart(part)
                                }
                                : undefined
                        }
                    />

                    {error && (
                        <div className="mx-auto flex w-full max-w-3xl items-center gap-2 px-4 pb-2">
                            <div className="flex flex-1 items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 nova-text-label-tiny text-red-600">
                                <span>{error}</span>
                                <Button
                                    rounded={false}
                                    size="xs"
                                    type="button"
                                    onClick={() => reload()}
                                    className="ml-auto shrink-0 bg-red-100 text-red-700 hover:bg-red-200"
                                >
                                    Retry
                                </Button>
                            </div>
                        </div>
                    )}

                    {!historySessionId &&
                        <>
                            <Modal
                                {...modalProps}
                            />
                            <div className="relative px-4 pb-4">
                                {!isAtBottom && (
                                    <Button
                                        variant="outline"
                                        type="button"
                                        onClick={() => scrollToBottomRef.current()}
                                        className="absolute -top-10 left-1/2 z-10 -translate-x-1/2 text-[#6B6B6B]"
                                    >
                                        ↓ Down
                                    </Button>
                                )}
                                <ChatInput
                                    input={input}
                                    onInputChange={setInput}
                                    onSubmit={handleSend}
                                    status={status}
                                    onStop={() => { }}
                                    attachedFiles={[]}
                                    onFilesChange={() => { }}
                                    taggedPart={taggedPart}
                                    onRemoveTaggedPart={() => setTaggedPart(null)}
                                    customButton={
                                        <Button
                                            onClick={() => setIsModalOpen(true)}
                                        >
                                            End session
                                        </Button>
                                    }
                                />
                            </div>

                            {/* <AnimatePresence>
                                {isDragging && <DropOverlay onFilesAdded={handleFilesAdded} />}
                            </AnimatePresence> */}
                        </>
                    }
                </div>
            </div>
        </div>
    )
}