import { FileUploadIcon, PastPaperCheckCircleIcon, PlusIcon } from "@/shared/assets/icons"
import { useCallback, useRef } from "react"
import type { UploadInfo } from "./types"
import { Button } from "@/shared"


type UploadButtonProps = {
    info: UploadInfo
    onFileSelect(e: React.ChangeEvent<HTMLInputElement>, id: string, type: "paper" | "mark"): void
}

function UploadButton({info, onFileSelect}: UploadButtonProps) {
    const fileInputPaperRef = useRef<HTMLInputElement>(null)
    const fileInputMarkRef = useRef<HTMLInputElement>(null)
    
    return (
        <div className="flex gap-x-1.5 p-1.5 h-30 border border-dashed border-[#E4DFDD] rounded-[20px]">
            <div className="flex-1 w-1/2">
                <button
                    className="flex items-center justify-center gap-x-1 w-full h-full p-2 rounded-[16px] nova-text-label-small text-[#242529] active:bg-[#FAF8F7] hover:nova-shadow-triple"
                    onClick={() => fileInputPaperRef.current?.click()}
                >
                    {info.paper ? (
                    <>
                        <PastPaperCheckCircleIcon />
                        <p className="w-full min-w-0 overflow-x-hidden text-ellipsis">{info.paper.name}</p>
                    </>
                    ) : (
                    <>
                        <FileUploadIcon />
                        Upload past paper
                    </>
                    )}
                </button>

                <input
                    ref={fileInputPaperRef}
                    type="file"
                    accept={".pdf"}
                    onChange={e => onFileSelect(e, info.id, "paper")}
                    hidden
                />
            </div>

            <div className="w-px h-3/4 bg-[#F4F4F5] rounded-full self-center" />

            <div className="flex-1 w-1/2">
                <button
                    className="flex items-center justify-center gap-x-1 w-full h-full p-2 rounded-[16px] nova-text-label-small text-[#242529] active:bg-[#FAF8F7] hover:nova-shadow-triple"
                    onClick={() => fileInputMarkRef.current?.click()}
                    disabled={info.paper === undefined}
                >
                    {info.mark ? (
                    <>
                        <PastPaperCheckCircleIcon />
                        <p className="w-full min-w-0 overflow-x-hidden text-ellipsis">{info.mark.name}</p>
                    </>
                    ) : (
                    <>
                        <FileUploadIcon />
                        Upload mark scheme
                    </>
                    )}
                </button>

                <input
                    ref={fileInputMarkRef}
                    type="file"
                    accept={".pdf"}
                    onChange={e => onFileSelect(e, info.id, "mark")}
                    hidden
                />
            </div>
        </div>
    )
}

type PastPapersUploadProps = {
    papersToUpload: UploadInfo[],
    onAddPaper(): void
    onFileSelect(file: File, id: string, type: "paper" | "mark"): void
}

export function PastPapersUpload({onAddPaper, onFileSelect, papersToUpload}: PastPapersUploadProps) {
    
    const handleFileSelect = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>, id: string, type: "paper" | "mark") => {
            const files = e.target.files
            if (!files) return
            
            onFileSelect(files[0], id, type)
        },
        [onFileSelect]
    )

    return (
        <div className="flex flex-col max-w-168 mx-auto gap-y-6 py-5">
            {papersToUpload.map(info => 
                <UploadButton
                    key={info.id}
                    info={info}
                    onFileSelect={handleFileSelect}
                />
            )}

            <Button
                variant="outline"
                className="self-start flex gap-x-1 items-center"
                onClick={onAddPaper}
            >
                <PlusIcon />
                Add more
            </Button>
        </div>  
    )
}