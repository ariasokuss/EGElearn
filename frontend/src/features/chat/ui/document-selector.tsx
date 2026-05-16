// "use client"

// import { useState, useRef, useEffect } from "react"

// import { cn } from "@/shared/lib"
// import type { FolderDocumentRead } from "@/entities/chat"
// import { AttachmentIcon } from "@/shared/assets/icons"

// type DocumentSelectorProps = {
//   documents: FolderDocumentRead[]
//   selectedId: string | null
//   onSelect: (id: string | null) => void
// }

// export function DocumentSelector({
//   documents,
//   selectedId,
//   onSelect,
// }: DocumentSelectorProps) {
//   const [isOpen, setIsOpen] = useState(false)
//   const containerRef = useRef<HTMLDivElement>(null)

//   const selectedDoc = documents.find((d) => d.id === selectedId)

//   useEffect(() => {
//     function handleClickOutside(e: MouseEvent) {
//       if (
//         containerRef.current &&
//         !containerRef.current.contains(e.target as Node)
//       ) {
//         setIsOpen(false)
//       }
//     }

//     if (isOpen) {
//       document.addEventListener("mousedown", handleClickOutside)
//       return () => document.removeEventListener("mousedown", handleClickOutside)
//     }
//   }, [isOpen])

//   if (documents.length === 0) return null

//   return (
//     <div ref={containerRef} className="relative">
//       <button
//         type="button"
//         onClick={() => setIsOpen((prev) => !prev)}
//         className={cn(
//           "flex items-center gap-1.5 rounded-lg px-2 py-1 transition-colors",
//           selectedDoc
//             ? "bg-[#F1ECE9] text-[#242529]"
//             : "text-[var(--ege-muted)] hover:bg-[var(--ege-surface)] hover:text-[var(--ege-text)]"
//         )}
//         aria-label="Select document"
//         title={selectedDoc ? selectedDoc.name : "Select document"}
//       >
//         <AttachmentIcon />
//         {selectedDoc && (
//           <span className="max-w-32 truncate text-xs font-medium">
//             {selectedDoc.name}
//           </span>
//         )}
//       </button>

//       {isOpen && (
//         <div className="absolute bottom-full left-0 mb-1 max-h-60 min-w-52 overflow-y-auto rounded-xl border border-[#E8E5E1] bg-white py-1 shadow-lg">
//           {selectedDoc && (
//             <button
//               type="button"
//               onClick={() => {
//                 onSelect(null)
//                 setIsOpen(false)
//               }}
//               className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-[#A1A1AA] transition-colors hover:bg-[#F0EFED]"
//             >
//               Clear selection
//             </button>
//           )}
//           {documents.map((doc) => (
//             <button
//               key={doc.id}
//               type="button"
//               onClick={() => {
//                 onSelect(doc.id)
//                 setIsOpen(false)
//               }}
//               className={cn(
//                 "flex w-full items-center gap-2 px-3 py-2 text-left nova-text-p-base transition-colors hover:bg-[#F0EFED]",
//                 doc.id === selectedId
//                   ? "font-medium text-[#242529]"
//                   : "text-[var(--ege-muted)]"
//               )}
//             >
//               <span
//                 className={cn(
//                   "h-1.5 w-1.5 shrink-0 rounded-full",
//                   doc.id === selectedId ? "bg-[#242529]" : "bg-transparent"
//                 )}
//               />
//               <span className="truncate">{doc.name}</span>
//               <span className="ml-auto shrink-0 nova-text-label-xxs text-[#A1A1AA]">
//                 {doc.page_count}p
//               </span>
//             </button>
//           ))}
//         </div>
//       )}
//     </div>
//   )
// }
