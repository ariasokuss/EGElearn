import { Button, cn } from "@/shared"
import { useEffect, useReducer } from "react"
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

type ChosenSectionsAction =
    | { type: "reset", sections: string[] }
    | { type: "toggle", index: number, sectionId: string }

function chosenSectionsReducer(state: string[], action: ChosenSectionsAction): string[] {
    if (action.type === "reset") return action.sections
    return state.map((value, index) =>
        index !== action.index ? value : value === action.sectionId ? "" : action.sectionId
    )
}

export function ExamChoose({ isOpen, blocks, onClose, title, submiting, initialSelection }: ExamChooseProps) {
    const [chosenSections, dispatchChosenSections] = useReducer(
        chosenSectionsReducer,
        initialSelection ?? blocks.map(() => "")
    )

    // Keep internal state in sync with saved selection while modal is closed
    useEffect(() => {
        if (!isOpen) {
            dispatchChosenSections({ type: "reset", sections: initialSelection ?? blocks.map(() => "") })
        }
    }, [isOpen, initialSelection, blocks])

    const handleClose = async (ids?: string[]) => {
        await onClose(ids)
    }

    if (typeof window === "undefined") return null

    return createPortal(
        <div
            className={cn(
                "z-[1000] fixed flex justify-center items-center inset-0 bg-black/55 transition-all",
                isOpen
                    ? "visible opacity-100"
                    : "invisible opacity-0"
            )}
        >
            <div className="w-full max-w-150 rounded-[20px] border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-1.5 text-[var(--ege-text)]">
                <div className="flex flex-col gap-5 rounded-[14px] bg-[var(--ege-surface-raised)] p-5">

                    <div className="flex flex-col gap-1.5">
                        <p className="nova-text-h-tiny">Темы по выбору для {title}</p>
                        <p className="nova-text-label-medium-regular text-[var(--ege-muted)]">
                            Выбери по одной теме
                            {blocks.length > 1
                                ? ` в каждом из ${blocks.length} блоков`
                                : " в этом блоке"
                            }
                        </p>
                    </div>

                    {blocks.map((block, ind) => (
                        <div key={ind} className="flex flex-col gap-2.5">
                            <div className="flex items-center gap-2">
                                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-[var(--ege-surface)] nova-text-label-small text-[var(--ege-muted)]">
                                    {ind + 1}
                                </span>
                                <p className="nova-text-label-medium text-[var(--ege-text)]">Выбери одну тему</p>
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
                                                    ? "border-[var(--ege-accent)] bg-[var(--ege-surface)] text-[var(--ege-text)]"
                                                    : "border-[var(--ege-border)] text-[var(--ege-muted)] hover:bg-[var(--ege-surface)] hover:text-[var(--ege-text)]"
                                            )}
                                            onClick={() => dispatchChosenSections({ type: "toggle", index: ind, sectionId: sect.id })}
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
                            Сохранить
                        </Button>
                    </div>
                </div>
            </div>
        </div>,
        document.body
    )
}
