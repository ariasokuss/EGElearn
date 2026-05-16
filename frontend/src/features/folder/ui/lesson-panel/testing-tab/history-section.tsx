// "use client";

// import { Button } from "@/shared";
// import type { TestRecord } from "./types";

// type Props = {
//   history: TestRecord[];
//   onView: (id: string) => void;
// };

// function byNewestFirst(a: TestRecord, b: TestRecord): number {
//   return b.date.getTime() - a.date.getTime();
// }

// export function HistorySection({ history, onView }: Props) {
//   if (history.length === 0) return null;
//   const sorted = [...history].sort(byNewestFirst);
//   return (
//     <div className="mt-6">
//       <h3 className="mb-3 text-[14px] font-semibold text-[#242529]">Previous attempts</h3>
//       <div className="flex flex-col gap-2">
//         {sorted.map((rec) => (
//           <div key={rec.id} className="flex items-center justify-between rounded-xl border border-[#E8E5E1] bg-white px-4 py-3">
//             <div>
//               <p className="text-[13px] font-medium text-[#242529]">
//                 {rec.percent}% — {rec.earned}/{rec.total} marks
//               </p>
//               <p className="text-[12px] text-[#71717A]">
//                 {rec.date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
//               </p>
//             </div>
//             <Button
//               variant="outline"
//               type="button"
//               onClick={() => onView(rec.id)}
//             >
//               View results
//             </Button>
//           </div>
//         ))}
//       </div>
//     </div>
//   );
// }
