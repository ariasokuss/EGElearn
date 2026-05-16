// "use client";

// import { useState } from "react";

// import type { OpenQuestionData } from "./parse-content";
// import { Md } from "./md";

// type OpenQuestionProps = {
//   data: OpenQuestionData;
//   variant: "short_answer" | "calculation";
// };

// export function OpenQuestion({ data, variant }: OpenQuestionProps) {
//   const [showAnswer, setShowAnswer] = useState(false);

//   const label = variant === "calculation" ? "Calculation" : "Short Answer";
//   const accentColor = variant === "calculation" ? "#7C3AED" : "#2563EB";
//   const accentBg = variant === "calculation" ? "#F5F3FF" : "#EFF6FF";
//   const accentBorder = variant === "calculation" ? "#C4B5FD" : "#BFDBFE";

//   return (
//     <div className="rounded-xl border border-[#E8E5E1] bg-white overflow-hidden">
//       <div
//         className="flex items-center justify-between border-b border-[#E8E5E1] px-4 py-2.5"
//         style={{ backgroundColor: accentBg, borderBottomColor: accentBorder }}
//       >
//         <div className="flex items-center gap-2">
//           <span
//             className="text-[11px] font-semibold uppercase tracking-wider"
//             style={{ color: accentColor }}
//           >
//             {label}
//           </span>
//           {data.marks > 0 && (
//             <span
//               className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
//               style={{
//                 backgroundColor: accentColor,
//                 color: "white",
//               }}
//             >
//               {data.marks} {data.marks === 1 ? "mark" : "marks"}
//             </span>
//           )}
//         </div>
//       </div>

//       <div className="px-4 py-4">
//         <div className="nova-text-p-base text-[#242529]">
//           <Md>{data.question}</Md>
//         </div>

//         {!showAnswer ? (
//           <button
//             type="button"
//             onClick={() => setShowAnswer(true)}
//             className="mt-4 rounded-lg border border-[#E8E5E1] bg-[#FAFAF8] px-4 py-2 text-[13px] font-medium text-[#71717A] transition-colors hover:bg-[#F1ECE9] hover:text-[#242529]"
//           >
//             Show answer
//           </button>
//         ) : (
//           <div className="mt-4 space-y-3">
//             {data.modelAnswer && (
//               <div
//                 className="rounded-lg border px-4 py-3"
//                 style={{ backgroundColor: accentBg, borderColor: accentBorder }}
//               >
//                 <p
//                   className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider"
//                   style={{ color: accentColor }}
//                 >
//                   Model answer
//                 </p>
//                 <div className="text-[13px] leading-5 text-[#242529]">
//                   <Md>{data.modelAnswer}</Md>
//                 </div>
//               </div>
//             )}
//           </div>
//         )}
//       </div>
//     </div>
//   );
// }
