"use client"

import { useState, useEffect, useMemo } from "react"
import type { RoadmapOut } from "@/shared/api/generated/model"
import { getRoadmapApi } from "@/features/folder/api/roadmap-api"
import { RoadmapSectionBlock } from "@/features/folder/ui/roadmap/roadmap-tree"
import { LoaderIcon } from "@/shared/assets/icons"

type TopicSelectionProps = {
  folderId: string
  selectedNodeIds: string[]
  onSelectionChange: (nodeIds: string[]) => void
}

export function TopicSelection({
  folderId,
  selectedNodeIds,
  onSelectionChange,
}: TopicSelectionProps) {
  const [roadmap, setRoadmap] = useState<RoadmapOut | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getRoadmapApi(folderId).then((data) => {
      if (!cancelled) {
        setRoadmap(data)
        setLoading(false)
      }
    })
    return () => { cancelled = true }
  }, [folderId])

  const selectedIds = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds])

  const handleToggleLesson = (id: string) => {
    if (selectedIds.has(id)) {
      onSelectionChange(selectedNodeIds.filter((nid) => nid !== id))
    } else {
      onSelectionChange([...selectedNodeIds, id])
    }
  }

  const handleToggleGroup = (ids: string[]) => {
    const allSelected = ids.every((id) => selectedIds.has(id))
    if (allSelected) {
      const idsToRemove = new Set(ids)
      onSelectionChange(selectedNodeIds.filter((id) => !idsToRemove.has(id)))
    } else {
      const current = new Set(selectedNodeIds)
      const merged = [...selectedNodeIds]
      for (const id of ids) {
        if (!current.has(id)) merged.push(id)
      }
      onSelectionChange(merged)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoaderIcon className="animate-spin text-[var(--ege-muted)]" />
      </div>
    )
  }

  if (!roadmap || roadmap.sections.length === 0) {
    return (
      <p className="py-12 text-center nova-text-p-base text-[var(--ege-muted)]">
        Сначала создай дорожную карту подготовки.
      </p>
    )
  }

  return (
    <div>
      <h2 className="mb-4 nova-text-h-tiny text-[var(--ege-text)]">
        Выбери темы из дорожной карты
      </h2>

      <div className="flex flex-col gap-4">
        {roadmap.sections.map((section) => (
          <RoadmapSectionBlock
            key={section.id}
            section={section}
            isCreating={true}
            selectedIds={selectedIds}
            onToggleLesson={handleToggleLesson}
            onToggleGroup={handleToggleGroup}
          />
        ))}
      </div>
    </div>
  )
}
