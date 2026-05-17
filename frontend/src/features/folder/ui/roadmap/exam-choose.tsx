import { Button, cn } from "@/shared"
import { useState } from "react"
import { createPortal } from "react-dom"

type SectionInfo = {
    id: string
    name: string
}

export type BlockInfo = SectionInfo[]


export type ExamChooseProps = {
    isOpen?: boolean
    onClose: (ids?: string[]) => Promise<void>
    title: string
    blocks: BlockInfo[]
    submiting?: boolean
    initialSelection?: string[]
}

export function ExamChoose({ isOpen, blocks, onClose, title, submiting, initialSelection }: ExamChooseProps) {
    const [chosenSections, setChosenSections] = useState<string[]>(
        initialSelection ?? blocks.map(() => "")
    )

    const handleClose = async (ids?: string[]) => {
        await onClose(ids)
    }

    if (typeof window === "undefined") return null

    return createPortal(
        <div
            className={cn(
                "z-[1000] fixed flex justify-center items-center inset-0 bg-black/50 transition-all",
                isOpen
                    ? "visible opacity-100"
                    : "invisible opacity-0"
            )}
        >
            <div className="p-1.5 w-full max-w-150 bg-white border border-[#F4F4F5] rounded-[20px]">
                <div className="flex flex-col gap-5 p-5 nova-shadow-sm rounded-[14px]">

                    <div className="flex flex-col gap-1.5">
                        <p className="nova-text-h-tiny">Выбери дополнительные темы для «{title}»</p>
                        <p className="nova-text-label-medium-regular text-[#72706F]">
                            Для «{title}» нужно выбрать по одной теме из
                            {blocks.length > 1
                                ? ` каждого из ${blocks.length} блоков`
                                : " этого блока"
                            }
                        </p>
                    </div>

                    {blocks.map((block, ind) => (
                        <div key={ind} className="flex flex-col gap-2.5">
                            <div className="flex items-center gap-2">
                                <span className="flex items-center justify-center size-5 shrink-0 rounded-full bg-[#F4F0EE] nova-text-label-small text-[#72706F]">
                                    {ind + 1}
                                </span>
                                <p className="nova-text-label-medium text-[#242529]">Выбери одну тему</p>
                            </div>

                            <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(block.length, 3)}, 1fr)` }}>
                                {block.map(sect => {
                                    const selected = sect.id === chosenSections[ind]
                                    return (
                                        <button
                                            key={sect.name}
                                            className={cn(
                                                "px-4 py-2.5 h-15 rounded-full nova-text-label-small text-center flex items-center justify-center transition-all border",
                                                selected
                                                    ? "bg-[#F4F0EE] text-[#242529] border-transparent"
                                                    : "text-[#72706F] border-transparent hover:bg-white hover:text-[#242529] hover:border-[#E2DDD9] hover:nova-shadow-sm"
                                            )}
                                            onClick={() => setChosenSections(prev => prev.map((v, i) =>
                                                i !== ind ? v : v === sect.id ? "" : sect.id
                                            ))}
                                        >
                                            {sect.name}
                                        </button>
                                    )
                                })}
                            </div>
                        </div>
                    ))}

                    <div className="flex gap-2 ml-auto pt-1">
                        <Button
                            variant="plain"
                            onClick={() => handleClose()}
                        >
                            Отмена
                        </Button>
                        <Button
                            disabled={chosenSections.some(id => id === "")}
                            isLoading={submiting}
                            onClick={() => handleClose(chosenSections)}
                        >
                            Сохранить выбор
                        </Button>
                    </div>
                </div>
            </div>
        </div>,
        document.body
    )
}
