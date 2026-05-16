"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";

import { DndContext, DragOverlay, closestCenter } from "@dnd-kit/core";
import { SortableContext, rectSortingStrategy } from "@dnd-kit/sortable";

import { reorderEgeFoldersApi } from "../../api/fixed-folders-api";
import { FIXED_FOLDER_SECTION_TITLE } from "../../lib/home-ui-copy";
import { useFolders } from "../../model/use-folders";
import { FolderItem } from "./folder-item";
import { FixedFolderSkeleton } from "./fixed-folder-skeleton";
import { SortableFolderItem } from "./sortable-folder-item";
import { useFolderDnd } from "./use-folder-dnd";

export function FixedFolderGrid() {
  const router = useRouter();
  const title = FIXED_FOLDER_SECTION_TITLE;
  const { egeFolders, loading, setEgeFolders } = useFolders();

  const persistOrder = useCallback(
    async (orderedIds: string[]) => {
      await reorderEgeFoldersApi(orderedIds);
    },
    [],
  );

  const {
    activeId,
    activeFolder,
    separatorAfterIndex,
    justDroppedId,
    sensors,
    folderIds,
    handlers,
  } = useFolderDnd({
    folders: egeFolders,
    setFolders: setEgeFolders,
    onOrderChange: persistOrder,
  });

  if (loading && egeFolders.length === 0) {
    return <FixedFolderSkeleton title={title} />;
  }

  return (
    <section aria-labelledby="fixed-folder-heading-ege">
      <h1
        id="fixed-folder-heading-ege"
        className="mt-4 mb-6 nova-text-label-base text-[var(--ege-text)]"
      >
        {title}
      </h1>

      <DndContext
        id="fixed-folders-ege"
        sensors={sensors}
        collisionDetection={closestCenter}
        {...handlers}
      >
        <SortableContext items={folderIds} strategy={rectSortingStrategy}>
          <div className="flex flex-wrap gap-3.5">
            {egeFolders.map((folder, index) => (
              <SortableFolderItem
                key={folder.id}
                id={folder.id}
                name={folder.name}
                pressed={folder.id === justDroppedId}
                showSeparatorAfter={index === separatorAfterIndex}
                isDraggingAny={!!activeId}
                readOnly
                onClick={() => router.push(`/folders/${folder.id}`)}
              />
            ))}
          </div>
        </SortableContext>

        <DragOverlay>
          {activeFolder && (
            <div className="opacity-80">
              <FolderItem name={activeFolder.name} pressed readOnly />
            </div>
          )}
        </DragOverlay>
      </DndContext>
    </section>
  );
}
