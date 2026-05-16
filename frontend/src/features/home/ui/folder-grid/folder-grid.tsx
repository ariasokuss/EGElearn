"use client";

/*
 * Custom folders (list + create + rename + DnD) - disabled: folders are fixed and loaded via
 * /api/v1/files/folders/ege (see FixedFolderGrid).
 *
 * Previous implementation used useFolders() with createFolder / updateFolder and CreateFolderCard.
 *
export function FolderGrid() {
  const { folders, setFolders, loading, createFolder, updateFolder } =
    useFolders();
  const [error, setError] = useState<string | null>(null);
  const {
    activeId,
    activeFolder,
    separatorAfterIndex,
    justDroppedId,
    sensors,
    folderIds,
    handlers,
  } = useFolderDnd({ folders, setFolders });

  const handleCreateFolder = useCallback(() => {
    setError(null);
    createFolder("New Folder").catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to create folder")
    );
  }, [createFolder]);

  const handleRename = useCallback(
    (id: string, name: string) => {
      setError(null);
      updateFolder(id, { name }).catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to rename folder")
      );
    },
    [updateFolder],
  );

  if (loading) {
    return <FolderGridSkeleton onCreateFolder={handleCreateFolder} />;
  }

  return (
    <div>
      <h1 className="mb-5.5 nova-text-label-base text-[#1D1B20]">
        My folders
      </h1>

      {error && (
        <p className="mb-4 nova-text-label-small-regular text-red-500">
          {error}
        </p>
      )}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        {...handlers}
      >
        <SortableContext items={folderIds} strategy={rectSortingStrategy}>
          <div className="flex flex-wrap gap-3">
            <CreateFolderCard onCreateFolder={handleCreateFolder} />

            {folders.map((folder, index) => (
              <SortableFolderItem
                key={folder.id}
                id={folder.id}
                name={folder.name}
                pressed={folder.id === justDroppedId}
                showSeparatorAfter={index === separatorAfterIndex}
                isDraggingAny={!!activeId}
                onRename={handleRename}
              />
            ))}
          </div>
        </SortableContext>

        <DragOverlay>
          {activeFolder && (
            <div className="opacity-80">
              <FolderItem name={activeFolder.name} pressed />
            </div>
          )}
        </DragOverlay>
      </DndContext>
    </div>
  );
}
*/

export function FolderGrid() {
  return null;
}
