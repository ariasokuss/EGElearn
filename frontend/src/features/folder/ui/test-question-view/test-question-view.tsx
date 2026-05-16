// "use client";

// import { ArrowsPointingInIcon, ChevronLeftIcon, ChevronRightIcon } from "@/shared/assets/icons";

// import { Md } from "../lesson-panel/block-renderer/md";
// import { TestMcqQuestion } from "../lesson-panel/testing-tab/test-mcq-question";
// import { TestOpenQuestion } from "../lesson-panel/testing-tab/test-open-question";
// import type { QuestionWithContext } from "../lesson-panel/testing-tab/types";
// import { Button } from "@/shared";

// export type TestQuestionViewProps = {
//   question: QuestionWithContext;
//   questionIndex: number;
//   total: number;
//   mcqAnswer: string | null;
//   onMcqSelect: (key: string) => void;
//   openAnswer: string;
//   onOpenAnswer: (value: string) => void;
//   onExit: VoidFunction;
//   onBack: VoidFunction;
//   onNext: VoidFunction;
//   isLast: boolean;
// };

// export function TestQuestionView({
//   question,
//   questionIndex,
//   total,
//   mcqAnswer,
//   onMcqSelect,
//   openAnswer,
//   onOpenAnswer,
//   onExit,
//   onBack,
//   onNext,
//   isLast,
// }: TestQuestionViewProps) {
//   const progress = ((questionIndex + 1) / total) * 100;

//   return (
//     <div className="flex h-full flex-col">
//       <div className="flex shrink-0 items-center gap-4 border-b border-[#E8E5E1] px-3 py-3">
//         <Button
//           iconOnly
//           rounded={false}
//           variant="plain"
//           type="button"
//           onClick={onExit}
//           className="flex shrink-0 items-center justify-center"
//           aria-label="Exit test"
//         >
//           <ArrowsPointingInIcon />
//         </Button>

//         <div className="flex flex-1 flex-col items-center gap-1.5">
//           <span className="text-[13px] text-[#71717A]">
//             Question {questionIndex + 1} of {total}
//           </span>
//           <div className="h-1 w-full max-w-xs rounded-full bg-[#E8E5E1]">
//             <div
//               className="h-1 rounded-full bg-[#242529] transition-all duration-300"
//               style={{ width: `${progress}%` }}
//             />
//           </div>
//         </div>

//         <div className="flex items-center gap-2">
//           <Button
//             size="sm"
//             variant="plain"
//             type="button"
//             disabled={questionIndex === 0}
//             onClick={onBack}
//             className="flex items-center justify-center gap-1 text-[#71717A] opacity-50 hover:opacity-100"
//           >
//             <ChevronLeftIcon className="h-3.5 w-3.5" />
//             Back
//           </Button>
//           <Button
//             size="sm"
//             type="button"
//             onClick={onNext}
//             className="flex items-center justify-center gap-1"
//           >
//             {isLast ? "Finish" : "Next"}
//             {!isLast && <ChevronRightIcon className="h-3.5 w-3.5" />}
//           </Button>
//         </div>
//       </div>

//       <div className="px-[24px] pt-[48px] flex flex-1 overflow-hidden">
//         <div className="flex-1 overflow-y-auto border-r border-[#E8E5E1] px-8 py-6">
//           {question.context ? (
//             <>
//               <h3 className="mb-4 text-[13px] font-semibold uppercase tracking-wider text-[#9B97A3]">
//                 Context
//               </h3>
//               <div className="nova-text-p-base text-[#242529]">
//                 <Md>{question.context}</Md>
//               </div>
//             </>
//           ) : (
//             <p className="text-[13px] text-[#A1A1AA]">No context for this question.</p>
//           )}
//         </div>

//         <div className="flex flex-1 flex-col px-8 py-6">
//           <div className="flex-1">
//             {question.type === "mcq" ? (
//               <TestMcqQuestion
//                 segment={question.segment}
//                 selected={mcqAnswer}
//                 onSelect={onMcqSelect}
//               />
//             ) : (
//               <TestOpenQuestion
//                 segment={question.segment}
//                 answer={openAnswer}
//                 onAnswerChange={onOpenAnswer}
//               />
//             )}
//             <Button
//               variant="outline"
//               size="xl"
//               type="button"
//               onClick={onNext}
//               className="mt-8 self-start"
//             >
//               {isLast ? "Finish" : "Next"}
//             </Button>
//           </div>
//         </div>
//       </div>
//     </div>
//   );
// }
