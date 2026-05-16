import { useCallback, useEffect, useRef, useState } from "react";

import { completeStepApi } from "../../api/lessons-api";
import { progressUpdateFromCompleteStep, useLessons } from "../../model/lessons-context";
import {
  checkAnswer,
  getInlineSession,
  resetInlineSession,
  saveSessionAnswer,
  type InlineQuestionMapEntry,
} from "../../api/lesson-test-api";
import { notify } from "@/shared/lib/notify";

export type AnswerRecord = {
  answer: string;
  questionType: "mcq" | "open";
  isCorrect: boolean | null;
  earnedMarks: number;
  totalMarks: number;
  feedback: string | null;
  recommendations: string | null;
  grading: boolean;
};

type QuestionMap = Record<string, InlineQuestionMapEntry>;

export function useInlineQuiz(lessonId: string, totalQuestions: number) {
  const { updateLessonProgress, markStepComplete, stepStatus, lessonMap } = useLessons();
  const lessonMapRef = useRef(lessonMap)
  useEffect(() => {
    lessonMapRef.current = lessonMap
  }, [lessonMap])
  const [boundLessonId, setBoundLessonId] = useState(lessonId);
  const [answers, setAnswers] = useState<Map<string, AnswerRecord>>(() => new Map());
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [questionMap, setQuestionMap] = useState<QuestionMap>({});
  const [loading, setLoading] = useState(true);
  const completedForLessonRef = useRef<string | null>(null);

  // Reset state when lesson changes
  if (boundLessonId !== lessonId) {
    setBoundLessonId(lessonId);
    setAnswers(new Map());
    setSessionId(null);
    setQuestionMap({});
    setLoading(true);
  }

  // Bootstrap: fetch or create inline session on mount / lesson change
  useEffect(() => {
    if (!lessonId) return;
    let cancelled = false;

    queueMicrotask(() => {
      setLoading(true);
    });
    getInlineSession(lessonId).then((data) => {
      if (cancelled || !data) {
        if (!cancelled) setLoading(false);
        return;
      }

      setSessionId(data.session_id);
      setQuestionMap(data.question_map);

      // Hydrate answers from backend
      const hydrated = new Map<string, AnswerRecord>();
      for (const [key, entry] of Object.entries(data.answers)) {
        const qType = data.question_map[key]?.type;
        hydrated.set(key, {
          answer: entry.answer,
          questionType: qType === "mcq" ? "mcq" : "open",
          isCorrect: entry.is_correct,
          earnedMarks: entry.earned_marks ?? 0,
          totalMarks: entry.total_marks,
          feedback: entry.feedback,
          recommendations: entry.recommendations ?? null,
          grading: false,
        });
      }
      setAnswers(hydrated);
      setLoading(false);
    });

    return () => { cancelled = true; };
  }, [lessonId]);

  // Auto-complete step 3 when all answered
  const allAnswered = totalQuestions > 0 && answers.size >= totalQuestions && answers.values().every(ans => !ans.grading);

  useEffect(() => {
    if (!allAnswered || completedForLessonRef.current === lessonId) return;
    completedForLessonRef.current = lessonId;

    if (stepStatus[lessonId]?.study || lessonMapRef.current[lessonId]?.lesson.study_star) return
    
    const answersValues = answers.values()
    const earnedMarks = answersValues.reduce((mark, ans) => mark + ans.earnedMarks, 0)
    const totalMarks = answersValues.reduce((mark, ans) => mark + ans.totalMarks, 0)
    
    if (earnedMarks / totalMarks < 0.7) return
    
    completeStepApi(lessonId, 1).then((r) => {
      if (!r) return;
      updateLessonProgress(lessonId, progressUpdateFromCompleteStep(r));
      markStepComplete(lessonId, 1);
      notify({ header: "Content star earned", content: "You've earned the content star for this lesson by answering all lesson questions with at least 70% accuracy!" })
    });
  }, [allAnswered, lessonId, updateLessonProgress, markStepComplete, stepStatus, answers]);

  const submitAnswer = useCallback(
    (blockId: string, questionIndex: number, record: AnswerRecord) => {
      const key = `${blockId}:${questionIndex}`;
      const qEntry = questionMap[key];

      if (!sessionId || !qEntry) {
        // Fallback: store locally if no session (shouldn't happen normally)
        setAnswers((prev) => {
          const next = new Map(prev);
          next.set(key, record);
          return next;
        });
        return;
      }

      if (qEntry.type === "mcq") {
        // MCQ: optimistic update + save_answer (instant grading on backend)
        setAnswers((prev) => {
          const next = new Map(prev);
          next.set(key, record);
          return next;
        });
        void saveSessionAnswer(sessionId, qEntry.question_id, record.answer);
      } else {
        // Open question: set grading state, call check_answer for LLM grading
        setAnswers((prev) => {
          const next = new Map(prev);
          next.set(key, { ...record, grading: true });
          return next;
        });

        checkAnswer(sessionId, qEntry.question_id, record.answer).then((result) => {
          if (!result) {
            // Grading failed — keep answer with grading=false
            setAnswers((prev) => {
              const next = new Map(prev);
              const existing = next.get(key);
              if (existing) {
                next.set(key, { ...existing, grading: false });
              }
              return next;
            });
            return;
          }

          setAnswers((prev) => {
            const next = new Map(prev);
            next.set(key, {
              answer: record.answer,
              questionType: "open",
              isCorrect: result.is_correct,
              earnedMarks: result.earned_marks ?? 0,
              totalMarks: result.total_marks,
              feedback: result.feedback ?? null,
              recommendations: result.recommendations ?? null,
              grading: false,
            });
            return next;
          });
        });
      }
    },
    [sessionId, questionMap],
  );

  const getAnswer = useCallback(
    (blockId: string, questionIndex: number): AnswerRecord | undefined => {
      return answers.get(`${blockId}:${questionIndex}`);
    },
    [answers],
  );

  const resetQuiz = useCallback(async () => {
    if (!lessonId) return;
    setLoading(true);
    const data = await resetInlineSession(lessonId);
    if (data) {
      setSessionId(data.session_id);
      setQuestionMap(data.question_map);
      setAnswers(new Map());
      completedForLessonRef.current = null;
    }
    setLoading(false);
  }, [lessonId]);

  return { answers, submitAnswer, getAnswer, allAnswered, loading, resetQuiz };
}
