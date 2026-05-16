"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getLessonTemplateAvailability,
  listLessonTests,
  type LessonTemplateAvailability,
} from "../../api/lesson-test-api";
import {
  getLessonHistoryApiV1FeynmanHistoryLessonLessonIdGet,
  getLessonResultsApiV1LearningLessonsLessonIdResultsGet,
} from "@/shared/api";
import type {
  LessonResultRead,
  SessionHistoryItem,
  TestSessionOut,
} from "@/shared/api/generated/model";

export type LessonTemplateMetaRow = { lessonId: string } & LessonTemplateAvailability;

export type LessonTabPrefetch = {
  lessonKey: string;
  testingTemplate: LessonTemplateMetaRow | null;
  testingTemplateLoading: boolean;
  testingHistory: TestSessionOut[] | null;
  testingHistoryLoading: boolean;
  feynmanHistory: SessionHistoryItem[] | null;
  feynmanHistoryLoading: boolean;
  lessonResults: LessonResultRead | null;
  lessonResultsLoading: boolean;
};

const emptyPrefetch = (lessonKey: string): LessonTabPrefetch => ({
  lessonKey,
  testingTemplate: null,
  testingTemplateLoading: true,
  testingHistory: null,
  testingHistoryLoading: true,
  feynmanHistory: null,
  feynmanHistoryLoading: true,
  lessonResults: null,
  lessonResultsLoading: true,
});

export type UseLessonTabPrefetchReturn = LessonTabPrefetch & {
  refreshTestingHistory: () => void;
  refreshLessonResults: () => void;
};

/**
 * Prefetches Explanation / Testing / Results data in parallel when the lesson opens
 * so tabs can paint from cache without waiting on each other.
 * `resetNonce` — increment to refetch everything (e.g. after Redo lesson).
 */
export function useLessonTabPrefetch(
  lessonId: string,
  folderId: string,
  resetNonce = 0,
): UseLessonTabPrefetchReturn {
  const [state, setState] = useState<LessonTabPrefetch>(() => emptyPrefetch(lessonId));

  const refreshTestingHistory = useCallback(() => {
    if (!lessonId) return;
    listLessonTests(lessonId, folderId).then((tests) => {
      setState((prev) => {
        if (prev.lessonKey !== lessonId) return prev;
        return { ...prev, testingHistory: tests, testingHistoryLoading: false };
      });
    });
  }, [lessonId, folderId]);

  const refreshLessonResults = useCallback(() => {
    if (!lessonId) return;
    getLessonResultsApiV1LearningLessonsLessonIdResultsGet(lessonId).then((resp) => {
      setState((prev) => {
        if (prev.lessonKey !== lessonId) return prev;
        if (resp.status === 200) return { ...prev, lessonResults: resp.data, lessonResultsLoading: false };
        return { ...prev, lessonResults: null, lessonResultsLoading: false };
      });
    }).catch(() => {
      setState((prev) => {
        if (prev.lessonKey !== lessonId) return prev;
        return { ...prev, lessonResults: null, lessonResultsLoading: false };
      });
    });
  }, [lessonId]);

  useEffect(() => {
    if (!lessonId) {
      queueMicrotask(() => {
        setState(emptyPrefetch(""));
      });
      return;
    }

    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) setState(emptyPrefetch(lessonId));
    });

    const mark = (patch: Partial<LessonTabPrefetch>) => {
      if (!cancelled) setState((prev) => ({ ...prev, ...patch }));
    };

    getLessonTemplateAvailability(lessonId)
      .then((result) => {
        mark({
          testingTemplate: { lessonId, ...result },
          testingTemplateLoading: false,
        });
      })
      .catch(() => {
        mark({
          testingTemplate: { lessonId, available: false, templateId: null },
          testingTemplateLoading: false,
        });
      });

    listLessonTests(lessonId, folderId)
      .then((tests) => {
        mark({ testingHistory: tests, testingHistoryLoading: false });
      })
      .catch(() => {
        mark({ testingHistory: [], testingHistoryLoading: false });
      });

    getLessonHistoryApiV1FeynmanHistoryLessonLessonIdGet(lessonId)
      .then((resp) => {
        if (resp.status === 200) {
          mark({ feynmanHistory: resp.data, feynmanHistoryLoading: false });
        } else {
          mark({ feynmanHistory: [], feynmanHistoryLoading: false });
        }
      })
      .catch(() => {
        mark({ feynmanHistory: [], feynmanHistoryLoading: false });
      });

    getLessonResultsApiV1LearningLessonsLessonIdResultsGet(lessonId)
      .then((resp) => {
        if (resp.status === 200) {
          mark({ lessonResults: resp.data, lessonResultsLoading: false });
        } else {
          mark({ lessonResults: null, lessonResultsLoading: false });
        }
      })
      .catch(() => {
        mark({ lessonResults: null, lessonResultsLoading: false });
      });

    return () => {
      cancelled = true;
    };
  }, [lessonId, folderId, resetNonce]);

  return { ...state, refreshTestingHistory, refreshLessonResults };
}
