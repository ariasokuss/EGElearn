"use client";

import { FixedFolderGrid } from "../folder-grid/fixed-folder-grid";

export function FolderSection() {
  return (
    <div className="mt-8 flex flex-col gap-6">
      <FixedFolderGrid />
    </div>
  );
}
