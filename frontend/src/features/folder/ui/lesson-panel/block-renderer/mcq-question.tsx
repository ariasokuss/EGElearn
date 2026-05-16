// "use client";

// import { useState } from "react";

// import { cn } from "@/shared/lib";

// import type { McqData } from "./parse-content";
// import { Md } from "./md";

// type McqQuestionProps = {
//   data: McqData;
// };

// const OPTION_STYLES = {
//   default: "border-[#E8E5E1] bg-white hover:bg-[#FAFAF8] cursor-pointer",
//   selected_correct: "border-[#22C55E] bg-[#F0FDF4]",
//   selected_wrong: "border-[#EF4444] bg-[#FEF2F2]",
//   unselected_correct: "border-[#22C55E] bg-[#F0FDF4] opacity-60",
// };

// export function McqQuestion({ data }: McqQuestionProps) {
//   const [selected, setSelected] = useState<string | null>(null);
//   const revealed = selected !== null;

//   function getOptionStyle(key: string): string {
//     if (!revealed) return OPTION_STYLES.default;
//     if (key === data.correct) return OPTION_STYLES.selected_correct;
//     if (key === selected) return OPTION_STYLES.selected_wrong;
//     return "border-[#E8E5E1] bg-white opacity-40";
//   }

//   return (
//     <div className="rounded-xl border border-[#E8E5E1] bg-white overflow-hidden">
//       <div className="flex items-center gap-2 border-b border-[#E8E5E1] px-4 py-2.5 bg-[#FAFAF8]">
//         <span className="text-[11px] font-semibold uppercase tracking-wider text-[#9B97A3]">
//           Multiple Choice
//         </span>
//       </div>

//       <div className="px-4 py-4">
//         <div className="mb-4 nova-text-p-large text-[#242529]">
//           <Md inline>{data.question}</Md>
//         </div>

//         <div className="flex flex-col gap-2">
//           {data.options.map((opt) => (
//             <button
//               key={opt.key}
//               type="button"
//               disabled={revealed}
//               onClick={() => setSelected(opt.key)}
//               className={cn(
//                 "flex items-start gap-3 rounded-lg border px-3.5 py-2.5 text-left transition-colors",
//                 getOptionStyle(opt.key)
//               )}
//             >
//               <span
//                 className={cn(
//                   "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold transition-colors",
//                   !revealed && "border-[#D1CEC8] text-[#9B97A3]",
//                   revealed && opt.key === data.correct && "border-[#22C55E] bg-[#22C55E] text-white",
//                   revealed && opt.key === selected && opt.key !== data.correct && "border-[#EF4444] bg-[#EF4444] text-white",
//                   revealed && opt.key !== selected && opt.key !== data.correct && "border-[#D1CEC8] text-[#9B97A3]"
//                 )}
//               >
//                 {opt.key}
//               </span>
//               <span className="text-[13px] leading-5 text-[#242529]">
//                 <Md inline>{opt.text}</Md>
//               </span>
//             </button>
//           ))}
//         </div>

//         {revealed && data.feedback && (
//           <div className="mt-3 rounded-lg bg-[#F0FDF4] border border-[#BBF7D0] px-3.5 py-2.5 text-[13px] leading-5 text-[#15803D]">
//             <Md inline>{data.feedback}</Md>
//           </div>
//         )}
//       </div>
//     </div>
//   );
// }
