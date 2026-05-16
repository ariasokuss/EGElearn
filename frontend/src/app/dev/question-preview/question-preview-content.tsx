"use client";

import { useState } from "react";

import { BackendTestQuestionView } from "@/features/folder/ui/lesson-panel/testing-tab/backend-test-question-view";
import type { TestQuestionOut } from "@/shared/api/generated/model";
import { inter } from "@/shared/config/fonts";
import { cn } from "@/shared/lib";

const MOCK_CONTEXT = `
2 Investment in the European Union, percentage of GDP, January 2019 to October 2021.

\`\`\`diagram
A line chart. Title: 2 Investment in the European Union, percentage of GDP, January 2019 to October 2021.
https://placehold.co/800x360/f4f4f5/52525b?text=Chart
\`\`\`

**Extract A**

Freeze in income tax thresholds from 2023 onwards

The freeze on the personal allowance, and the basic and higher-rate income tax bands in England, Wales and Northern Ireland will be extended to April 2028. While this freeze may not look like a tax rise on the face of it, having thresholds that fail to rise in line with salaries, people will still end up paying more tax on their income – particularly if they end up in a higher tax band as a result.

The biggest change announced in the Autumn Statement 2022 was the reduction of the additional-rate income tax threshold, dropping from £150 000 to £125 140 from 6 April 2023. It is estimated around 250 000 taxpayers will be pushed into the additional rate tax band, paying 45% tax on any income above the new limit.

The Chancellor said lowering the additional rate threshold means that a person earning £150 000 will pay an extra £1 200 income tax per year.

(Source adapted from: https://www.which.co.uk/news/article/6-tax-changes-to-watch-out-for-in-2023)

(Source: https://www.ons.gov.uk/economy/grossdomesticproductgdp/timeseries/dgd8/ukea)
`.trim();

const MOCK_QUESTION: TestQuestionOut = {
  id: "dev-preview-question-1",
  index: 0,
  type: "mcq",
  question:
    "Which one of the following is the **percentage point fall** in investment between April 2020 and July 2020?",
  options: ["0.1", "0.6", "2.1", "8.9"],
  hint: "Find the values for April 2020 and July 2020 on the graph, then subtract.",
  points: 1,
  context: MOCK_CONTEXT,
};

export function QuestionPreviewContent() {
  const [mcq, setMcq] = useState<number | null>(1);

  return (
    <div
      className={cn(
        "flex h-svh flex-col overflow-hidden bg-white antialiased",
        inter.className,
        inter.variable,
      )}
    >
      <p className="shrink-0 border-b border-[#E4E4E7] bg-[#FAFAF8] px-4 py-2 text-[#71717A] nova-text-label-tiny">
        <span className="text-[#A1A1AA]">[dev]</span> /dev/question-preview — mock data
      </p>
      <div className="h-full min-h-0 min-w-0 flex-1 overflow-hidden">
        <div className="h-full min-h-0">
          <BackendTestQuestionView
            question={MOCK_QUESTION}
            questionIndex={2}
            total={5}
            mcqAnswer={mcq}
            onMcqSelect={setMcq}
            openAnswer=""
            onOpenAnswer={() => {}}
            onBack={() => {}}
            onNext={() => {}}
            isLast={false}
            isExpanded
          />
        </div>
      </div>
    </div>
  );
}
