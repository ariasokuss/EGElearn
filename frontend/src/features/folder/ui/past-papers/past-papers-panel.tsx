import { ArrowsPointingInIcon, ArrowsPointingOutIcon, XMarkIcon } from "@/shared/assets/icons"
import { PastPapersUpload } from "./past-papers-upload"
import { PastPapersStart } from "./past-papers-start"
import { PastPaperTest } from "./past-papers-test"
import { useState } from "react"
import { nanoid } from "nanoid"
import { usePastPapers } from "../../model/past-papers-context"
import type { TestSessionOut } from "@/shared/api/generated/model"
import { Button } from "@/shared"
import { Tippy } from "@/shared/ui"

import type { PastPaperTestInfo, UploadInfo } from "./types"
export type { UploadInfo } from "./types"

type PastPapersPanelProps = {
  folderId: string
  pastPapersListVisible: boolean
  pastPapersUploadVisible: boolean
  pastPaperTesting: PastPaperTestInfo,
  chosenPastPaperId: string | null
  onTogglePastPapersList(): void
  onCollapsePastPapersList(): void
  onClosePanel(): void
  setPastPaperTesting(value: PastPaperTestInfo): void
  onTestEnd(session: TestSessionOut): void
  onPastPaperSessionsRefresh?: () => void
}

export function PastPapersPanel({ folderId, onTogglePastPapersList, onCollapsePastPapersList, onClosePanel, onTestEnd, setPastPaperTesting, chosenPastPaperId, pastPaperTesting, pastPapersListVisible, pastPapersUploadVisible, onPastPaperSessionsRefresh }: PastPapersPanelProps) {
  const [papersToUpload, setPapersToUpload] = useState<UploadInfo[]>([{ id: nanoid() }])
  const { addPapersToUpload } = usePastPapers()

  if (pastPaperTesting.status !== "none" && chosenPastPaperId)
    return (
      <PastPaperTest
        folderId={folderId}
        isPastPapersListOpen={pastPapersListVisible}
        onHomeClick={onClosePanel}
        onClosePanel={onClosePanel}
        onTogglePastPapersList={onTogglePastPapersList}
        onCollapsePastPapersList={onCollapsePastPapersList}
        onTestExit={onClosePanel}
        onArrowsClick={onTogglePastPapersList}
        onTestEnd={onTestEnd}
        testInfo={pastPaperTesting}
      />
    )

  const onAddPaper = () => setPapersToUpload(prev => [...prev, { id: nanoid() }])
  const onFileSelect = (file: File, id: string, type: "paper" | "mark") => {
    setPapersToUpload(prev => prev.map(paper =>
      paper.id !== id
        ? paper
        : type === "paper"
          ? { id, paper: file }
          : { id, paper: paper.paper, mark: file }
    ))
  }
  const onPapersUpload = () => {
    addPapersToUpload(...papersToUpload.filter(paper => paper.paper !== undefined))
    onClosePanel()
  }

  const hasPaperWithoutMark = papersToUpload.some(p => p.paper !== undefined && p.mark === undefined)
  const hasAnyPaper = papersToUpload.some(p => p.paper !== undefined)
  const uploadDisabled = !hasAnyPaper || hasPaperWithoutMark

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="relative flex shrink-0 items-center px-5 py-2.75">
        <div className="flex">
          <Button
            iconOnly
            rounded={false}
            variant="plain"
            type="button"
            onClick={onClosePanel}
            className="flex shrink-0 items-center justify-center"
            aria-label={pastPapersListVisible ? "Hide past papers list" : "Show past papers list"}
          >
            <XMarkIcon className="size-4.5" />
          </Button>
          <Button
            iconOnly
            rounded={false}
            variant="plain"
            type="button"
            onClick={onTogglePastPapersList}
            className="flex shrink-0 items-center justify-center"
            aria-label={pastPapersListVisible ? "Hide past papers list" : "Show past papers list"}
          >
            {pastPapersListVisible ? <ArrowsPointingOutIcon /> : <ArrowsPointingInIcon />}
          </Button>
        </div>

        {pastPapersUploadVisible &&
          <>
            <p className="absolute w-full text-center pointer-events-none nova-text-h-small-sb text-[#242529]">Add past papers to solve them on NovaLearn</p>

            <div className="ml-auto">
              <Tippy
                content="A mark scheme must be uploaded first"
                disabled={!hasPaperWithoutMark}
              >
                <Button
                  size="l"
                  type="button"
                  onClick={onPapersUpload}
                  disabled={uploadDisabled}
                >
                  Upload
                </Button>
              </Tippy>
            </div>
          </>
        }
      </div>

      <div className="flex-1 overflow-y-auto">
        {pastPapersUploadVisible
          ? <PastPapersUpload
            papersToUpload={papersToUpload}
            onAddPaper={onAddPaper}
            onFileSelect={onFileSelect}
          />
          : <PastPapersStart
            selectedPastPaperId={chosenPastPaperId}
            setPastPaperTesting={setPastPaperTesting}
            onSessionsRefresh={onPastPaperSessionsRefresh}
          />
        }
      </div>
    </div>
  )
}
