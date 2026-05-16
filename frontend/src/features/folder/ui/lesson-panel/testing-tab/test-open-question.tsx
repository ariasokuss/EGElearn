// "use client";

// import { memo, useState } from "react";
// import TextareaAutosize from "react-textarea-autosize";

// import { Md } from "../block-renderer/md";
// import { parseOpenQuestion, type DirectiveSegment } from "../block-renderer/parse-content";

// import {
//   OPEN_ANSWER_MAX_LENGTH,
//   OPEN_ANSWER_TEXTAREA_MAX_ROWS,
// } from "./open-answer-constants";
// import { Button } from "@/shared";

// const TestOpenQuestionStem = memo(function TestOpenQuestionStem({
//   questionText,
//   marksLabel,
// }: {
//   questionText: string;
//   marksLabel: string | null;
// }) {
//   return (
//     <div className="flex items-start justify-between gap-3">
//       <p className="nova-text-label-base text-[#242529]">
//         <Md>{questionText}</Md>
//       </p>
//       {marksLabel ? (
//         <span className="mt-0.5 shrink-0 rounded-full border border-[#E8E5E1] bg-[#FAFAF8] px-2.5 py-0.5 text-[11px] font-medium text-[#71717A]">
//           {marksLabel}
//         </span>
//       ) : null}
//     </div>
//   );
// });

// type Props = {
//   segment: DirectiveSegment;
//   answer: string;
//   onAnswerChange: (value: string) => void;
// };

// export function TestOpenQuestion({ segment, answer, onAnswerChange }: Props) {
//   const [revealed, setRevealed] = useState(false);

//   const variant = segment.subtype === "calculation" ? "calculation" : "short_answer";
//   const data = parseOpenQuestion(segment.body, segment.label);

//   const accentColor = variant === "calculation" ? "#7C3AED" : "#2563EB";
//   const accentBg = variant === "calculation" ? "#F5F3FF" : "#EFF6FF";
//   const accentBorder = variant === "calculation" ? "#C4B5FD" : "#BFDBFE";

//   const marksLabel =
//     data.marks != null ? `${data.marks} mark${data.marks !== 1 ? "s" : ""}` : null;

//   return (
//     <div className="flex flex-col gap-4">
//       <TestOpenQuestionStem questionText={data.question} marksLabel={marksLabel} />

//       <TextareaAutosize
//         value={answer}
//         onChange={(e) =>
//           onAnswerChange(e.target.value.slice(0, OPEN_ANSWER_MAX_LENGTH))
//         }
//         placeholder="Write your answer here…"
//         minRows={6}
//         maxRows={OPEN_ANSWER_TEXTAREA_MAX_ROWS}
//         maxLength={OPEN_ANSWER_MAX_LENGTH}
//         className="w-full resize-none rounded-xl border border-[#E8E5E1] bg-white px-4 py-3 text-[13px] leading-5 text-[#242529] placeholder-[#A1A1AA] outline-none transition-colors focus:border-[#3F3C47] focus:ring-0"
//       />

//       {!revealed ? (
//         <Button
//           variant="outline"
//           size="l"
//           rounded={false}
//           type="button"
//           onClick={() => setRevealed(true)}
//           className="self-start text-[#71717A] hover:text-[#242529]"
//         >
//           Show answer
//         </Button>
//       ) : (
//         <div className="flex flex-col gap-3">
//           {answer.trim() && (
//             <div className="rounded-xl border border-[#E8E5E1] bg-[#FAFAF8] px-4 py-3">
//               <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#9B97A3]">
//                 Your answer
//               </p>
//               <p className="text-[13px] leading-5 text-[#3F3C47]">{answer}</p>
//             </div>
//           )}

//           {data.markscheme && (
//             <div className="rounded-xl border border-[#E8E5E1] bg-[#FAFAF8] px-4 py-3">
//               <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#9B97A3]">
//                 Mark scheme
//               </p>
//               <div className="text-[13px] leading-5 text-[#3F3C47]">
//                 <Md>{data.markscheme}</Md>
//               </div>
//             </div>
//           )}

//           {data.modelAnswer && (
//             <div
//               className="rounded-xl border px-4 py-3"
//               style={{ backgroundColor: accentBg, borderColor: accentBorder }}
//             >
//               <p
//                 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider"
//                 style={{ color: accentColor }}
//               >
//                 Model answer
//               </p>
//               <div className="text-[13px] leading-5 text-[#242529]">
//                 <Md>{data.modelAnswer}</Md>
//               </div>
//             </div>
//           )}
//         </div>
//       )}
//     </div>
//   );
// }
