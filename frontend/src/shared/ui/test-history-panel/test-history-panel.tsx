import { TestHistory } from "@/features/practice-questions/ui/test-history";
import type { TemplateWithProgress } from "@/features/practice-questions/api";
import { TestSessionOut } from "@/shared/api/generated/model";
import { Button } from "../button";
import { useEffect, useMemo, useState } from "react";
import { cn } from "@/shared";

type sessionGroup = {
    name: string
    sessions: TestSessionOut[]
}

const LEGACY_GROUP_NAMES: Record<string, string> = {
    "Started attempts": "Начатые попытки",
    "Completed attempts": "Завершённые попытки",
    "Not started tests": "Не начатые тесты",
    "Started tests": "Начатые тесты",
    "Completed tests": "Завершённые тесты",
}

type TestHistoryPanelProps = {
    activeGroup: string
    setActiveGroup: (group: string) => void
    sessions: TestSessionOut[]
    loading: boolean
    onSelect: (session: TestSessionOut) => void
    templates?: TemplateWithProgress[]
    onTemplatesRefresh?: () => void
    onCancelGeneration?: (templateId: string) => void
    onRetryGeneration?: (templateId: string) => void
    onDeleteTemplate?: (templateId: string) => void,
    tab: "past-papers" | "practice-questions"
}

export function TestHistoryPanel({
    loading,
    onSelect,
    sessions,
    templates,
    onTemplatesRefresh,
    onCancelGeneration,
    onRetryGeneration,
    onDeleteTemplate,
    activeGroup,
    setActiveGroup,
    tab
}: TestHistoryPanelProps) {
    const [groupIndex, setGroupIndex] = useState(-1)

    const hideScoreForIncompleteSessions =
        (tab === "past-papers" && groupIndex === 0) ||
        (tab === "practice-questions" && groupIndex !== 2)

    const sessionGroups = useMemo<sessionGroup[]>(() => {
        const groups: sessionGroup[] = tab === "past-papers" ? [
            { name: "Начатые попытки", sessions: [] },
            { name: "Завершённые попытки", sessions: [] },
        ] : [
            { name: "Не начатые тесты", sessions: [] },
            { name: "Начатые тесты", sessions: [] },
            { name: "Завершённые тесты", sessions: [] },
        ]

        sessions.forEach(session => {
            if (session.status === "not_started") {
                if (tab !== "past-papers") {
                    groups[0].sessions.push(session)
                }
            } else if (session.status === "active") {
                groups[tab === "past-papers" ? 0 : 1].sessions.push(session)
            } else {
                groups[groups.length - 1].sessions.push(session)
            }
        })

        return groups
    }, [tab, sessions])

    useEffect(() => {
        if (!activeGroup) return
        const localizedGroup = LEGACY_GROUP_NAMES[activeGroup]
        if (localizedGroup) {
            setActiveGroup(localizedGroup)
            return
        }
        requestAnimationFrame(() => setGroupIndex(sessionGroups.findIndex(group => group.name === activeGroup)))
    }, [activeGroup, sessionGroups, setActiveGroup])

    return (
        <div
            className="absolute top-0 right-7 h-full"
            style={{ pointerEvents: activeGroup ? "unset" : "none" }}
        >
            <div
                className="relative flex flex-col overflow-x-hidden h-full border-l border-[#F4F4F5] bg-white pr-4"
                style={{
                    overflowY: activeGroup ? "auto" : "hidden"
                }}
            >   
                <div className="flex flex-col w-fit ml-auto gap-2 pt-4 pl-4 pb-1">
                    {sessionGroups.map(group => 
                        <Button
                            key={group.name}
                            variant="outline"
                            size="xs"
                            className={cn("flex gap-x-1 items-center pointer-events-auto", activeGroup === group.name && "bg-nova-200 hover:bg-nova-200")}
                            onClick={() => setActiveGroup(activeGroup === group.name ? "" : group.name)}
                        >
                            {group.name}
                        </Button>
                    )}
                </div>
                <div
                    className="relative h-full border-l border-[#F4F4F5] bg-white transition-all duration-300 ease-in-out"
                    style={{ 
                        opacity: activeGroup ? 1 : 0, 
                        width: activeGroup ? "calc(clamp(300px, 25vw, 400px) - 17px)" : 100,
                        pointerEvents: activeGroup ? "auto" : "none" 
                    }}
                >
                    <div className="min-w-75">
                        <TestHistory
                            sessions={groupIndex === -1 ? [] : sessionGroups[groupIndex].sessions}
                            loading={loading}
                            onSelect={onSelect}
                            templates={templates}
                            onTemplatesRefresh={onTemplatesRefresh}
                            onCancelGeneration={onCancelGeneration}
                            onRetryGeneration={onRetryGeneration}
                            onDeleteTemplate={onDeleteTemplate}
                            historyName={groupIndex === -1 ? undefined : sessionGroups[groupIndex].name}
                            hideScoreForIncompleteSessions={hideScoreForIncompleteSessions}
                        />
                    </div>
                </div>
            </div>
        </div>
    )
}
