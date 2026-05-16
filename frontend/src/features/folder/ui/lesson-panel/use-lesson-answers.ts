// import { useCallback, useEffect, useRef, useState } from "react";

// import { completeStepApi } from "../../api/lessons-api";
// import { progressUpdateFromCompleteStep, useLessons } from "../../model/lessons-context";
// import { notify } from "@/shared/lib/notify";

// export type AnswerRecord = {
//   answer: string;
//   questionType: "mcq" | "open";
//   isCorrect: boolean | null;
//   earnedMarks: number;
//   totalMarks: number;
// };

// export function useLessonAnswers(lessonId: string, totalQuestions: number) {
//   const { updateLessonProgress, markStepComplete } = useLessons();
//   const [boundLessonId, setBoundLessonId] = useState(lessonId);
//   const [answers, setAnswers] = useState<Map<string, AnswerRecord>>(() => new Map());
//   const completedForLessonRef = useRef<string | null>(null);

//   if (boundLessonId !== lessonId) {
//     setBoundLessonId(lessonId);
//     setAnswers(new Map());
//   }

//   const submitAnswer = useCallback((blockId: string, questionIndex: number, record: AnswerRecord) => {
//     setAnswers((prev) => {
//       const next = new Map(prev);
//       next.set(`${blockId}:${questionIndex}`, record);
//       return next;
//     });
//   }, []);

//   const getAnswer = useCallback(
//     (blockId: string, questionIndex: number): AnswerRecord | undefined => {
//       return answers.get(`${blockId}:${questionIndex}`);
//     },
//     [answers],
//   );

//   const allAnswered = totalQuestions > 0 && answers.size >= totalQuestions;

//   useEffect(() => {
//     if (!allAnswered || completedForLessonRef.current === lessonId) return;
//     completedForLessonRef.current = lessonId;
//     completeStepApi(lessonId, 3).then(r => {
//       if (!r) return;
//       updateLessonProgress(lessonId, progressUpdateFromCompleteStep(r));
//       markStepComplete(lessonId, 3);
//       notify({ header: "Test star earned", content: "You've earned the test star for this lesson because you scored over 70% on the test!" })
//     });
//   }, [allAnswered, lessonId, updateLessonProgress, markStepComplete]);

//   return { answers, submitAnswer, getAnswer, allAnswered };
// }
