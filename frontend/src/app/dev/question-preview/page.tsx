import type { Metadata } from "next";

import { QuestionPreviewContent } from "./question-preview-content";

export const metadata: Metadata = {
  title: "Question UI preview (dev)",
  robots: { index: false, follow: false },
};

export default function QuestionPreviewPage() {
  return <QuestionPreviewContent />;
}
