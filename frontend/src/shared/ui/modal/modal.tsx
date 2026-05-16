import { Button, cn } from "@/shared"
import { CircleInfoIcon, XMarkIcon } from "@/shared/assets/icons"

export type ModalProps = {
    isOpen?: boolean,
    onPrimaryClick?(): void
    onSecondaryClick?(): void
    primaryButtonText: string
    secondaryButtonText: string
    onXClick?(): void
    title: string
    description?: string
    /** When true, uses absolute positioning scoped to the nearest relative parent instead of fixed fullscreen. */
    contained?: boolean
}

export function Modal({isOpen, primaryButtonText, secondaryButtonText, onPrimaryClick, onSecondaryClick, onXClick, title, description, contained}: ModalProps) {
    return (
        <div
            className={cn(
                "z-100 flex justify-center items-center inset-0 bg-black/50 transition-all",
                contained ? "absolute" : "fixed",
                isOpen
                    ? "visible opacity-100"
                    : "invisible opacity-0"
            )}
        >
            <div className="flex flex-col w-full max-w-200 h-117 bg-white border border-[#F4F4F5] rounded-[20px]">
                {onXClick && 
                    <div className="w-full p-1.5 border-b border-[#F4F4F5]">
                        <Button
                            iconOnly
                            size="sm"
                            variant="outline"
                            className="flex justify-center items-center"
                            onClick={onXClick}
                        >
                            <XMarkIcon className="size-4" />
                        </Button>
                    </div>
                }
                <div className="w-full h-full p-1.5">
                    <div className="flex flex-col gap-y-6 justify-center items-center w-full h-full p-12 rounded-[16px] nova-shadow-sm">
                        <CircleInfoIcon />

                        <div className="flex flex-col items-center w-87">
                            <p className="text-center nova-text-label-base text-[#242529]">{title}</p>
                            {description && <p className="mt-2 text-center nova-text-label-small text-[#71717A]">{description}</p>}
                            <div className="mt-3 flex gap-x-2 nova-text-label-small text-[#242529]">
                                <Button
                                    onClick={onPrimaryClick}
                                >
                                    {primaryButtonText}
                                </Button>
                                <Button
                                    variant="plain"
                                    onClick={onSecondaryClick}
                                >
                                    {secondaryButtonText}
                                </Button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}