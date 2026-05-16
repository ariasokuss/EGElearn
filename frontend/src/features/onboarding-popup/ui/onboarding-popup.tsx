"use client"

import { Button, cn } from "@/shared"
import { CircleInfoIcon, XMarkIcon } from "@/shared/assets/icons"
import { useOnboardingPopup } from "../model/use-onboarding-popup"
import { useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"

export function OnboardingPopup() {
    const { close, isOpen } = useOnboardingPopup()

    const videoRef = useRef<HTMLVideoElement>(null)
    const watchedVideoFully = useRef(false)
    const shouldResumeAfterWarning = useRef(false)
    const [showWarning, setShowWarning] = useState(false)
    const [hideVideoElement, setHideVideoElement] = useState(!isOpen)

    const pauseVideo = () => {
        const video = videoRef.current
        if (!video) {
            shouldResumeAfterWarning.current = false
            return
        }
        shouldResumeAfterWarning.current = !video.paused && !video.ended
        video.pause()
    }

    const closeWithReset = () => {
        pauseVideo()
        setShowWarning(false)
        watchedVideoFully.current = false
        shouldResumeAfterWarning.current = false
        close()
    }

    const handleXClick = () => {
        const video = videoRef.current
        if (!video) {
            closeWithReset()
            return
        }

        if (!watchedVideoFully.current) {
            pauseVideo()
            setShowWarning(true)
            return
        }
        closeWithReset()
    }

    const handleKeepWatching = () => {
        setShowWarning(false)
        if (!shouldResumeAfterWarning.current) return
        shouldResumeAfterWarning.current = false
        const video = videoRef.current
        if (!video) return
        void video.play().catch(() => {
            /* ignore autoplay policy errors */
        })
    }

    useEffect(() => {
        if (isOpen) {
            queueMicrotask(() => {
                setHideVideoElement(false)
            })
            return
        }
        queueMicrotask(() => {
            setShowWarning(false)
        })
        setTimeout(() => {
            setHideVideoElement(true)
        }, 200);
        watchedVideoFully.current = false
        shouldResumeAfterWarning.current = false
    }, [isOpen])

    if (typeof window === "undefined") return null

    return createPortal(
        <div
            className={cn(
                "z-[1000] flex justify-center items-center inset-0 bg-black/50 transition-all duration-200 fixed",
                isOpen
                    ? "visible opacity-100"
                    : "invisible opacity-0"
            )}
        >
            <div className="flex flex-col w-full max-w-200 bg-white border border-[#F4F4F5] rounded-[20px]">
                <div className="flex gap-3 w-full p-1.5 border-b border-[#F4F4F5]">
                    <Button
                        iconOnly
                        size="sm"
                        variant="outline"
                        className="flex justify-center items-center"
                        onClick={handleXClick}
                    >
                        <XMarkIcon className="size-4" />
                    </Button>
                    <p className="pr-10 nova-text-label-base font-semibold text-center flex-1">Выбери предмет ЕГЭ</p>
                </div>
                <div className="relative flex justify-center items-center w-full h-full p-1.5">
                    {!hideVideoElement && (
                        <div className={cn("relative z-10 w-full max-h-full rounded-[14px] overflow-hidden transition-all", showWarning ? "opacity-0 invisible pointer-events-none" : "visible")}>
                            <video
                                ref={videoRef}
                                className="block w-full max-h-full"
                                controls
                                preload="metadata"
                                playsInline
                                onEnded={() => { watchedVideoFully.current = true }}
                            >
                                <source src="/Novalearn Onboarding.mp4#t=0.1" type="video/mp4" />
                                <source src="/Novalearn Onboarding.mov#t=0.1" type="video/quicktime" />
                                Открой уроки и практику
                            </video>
                        </div>
                    )}

                    <div className={cn("absolute inset-1.5 flex flex-col gap-y-6 justify-center items-center p-12 rounded-[16px] nova-shadow-sm transition-all", showWarning ? "visible" : "invisible")}>
                        <CircleInfoIcon />

                        <div className="flex flex-col items-center w-90">
                            <p className="text-center nova-text-label-base text-[#242529]">Разбирай ошибки с YandexGPT</p>
                            <p className="mt-2 text-center nova-text-label-small text-[#71717A]">Открой уроки и практику</p>
                            <div className="mt-3 flex gap-x-2 nova-text-label-small text-[#242529]">
                                <Button
                                    onClick={handleKeepWatching}
                                >
                                    Продолжить
                                </Button>
                                <Button
                                    variant="plain"
                                    onClick={closeWithReset}
                                >
                                    Закрыть
                                </Button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>,
        document.body
    )
}
