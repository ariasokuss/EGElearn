"use client";

import { Button } from "@/shared";
import { MarkIcon } from "@/shared/assets/icons";

const cardShadow =
  "shadow-[0px_4px_6px_-1px_#0000000A,0px_2px_4px_-2px_#00000005]";

const COMPARISON_ROWS: { label: string; values: [string, string, string] }[] = [
  {
    label: "Access to lessons",
    values: [
      "1 topic per subject",
      "All topics for all subjects",
      "All topics for all subjects",
    ],
  },
  {
    label: "Chat messages",
    values: ["50", "300 per month", "800 per month"],
  },
  {
    label: "Feynman",
    values: ["60 per month", "60 per month", "150 per month"],
  },
  {
    label: "Custom tests",
    values: ["60 per month", "25", "75"],
  },
  {
    label: "Nova tests (per subject)",
    values: ["1", "3", "5"],
  },
  {
    label: "MyPastPapers",
    values: ["2", "3 per subject", "Unlimited"],
  },
];

const PLANS = [
  {
    name: "Free",
    priceLine: "Free using",
    subtitle: "Explore, prepare for exams",
    cta: "Currently in use",
    ctaStyle: "muted" as const,
  },
  {
    name: "Plus",
    priceLine: "$12 per month",
    subtitle: "Explore, prepare for exams",
    cta: "Get Plus plan",
    ctaStyle: "primary" as const,
  },
  {
    name: "Pro",
    priceLine: "$17 per month",
    subtitle: "Explore, prepare for exams",
    cta: "Get Pro annual plan",
    ctaStyle: "primary" as const,
  },
];

export function UpgradePanel() {
  return (
    <div className="mx-auto max-w-[1000px] px-6 py-8">
      <div className="mt-8 rounded-2xl border border-[#E8E5E180] bg-white pt-[16px] px-[8px] shadow-[0px_4px_6px_-1px_#0000000A,0px_2px_4px_-2px_#00000005]">
        <h1 className="mt-[12px] mx-[16px] nova-text-h-tiny text-[#1D1B20]">
          Plans that grow with you
        </h1>

        <div className="mt-7 mb-[8px] grid grid-cols-1 gap-2.5 sm:gap-2.5 lg:grid-cols-3">
          {PLANS.map((plan, colIndex) => (
            <div
              key={plan.name}
              className={`flex h-full min-h-0 flex-col rounded-2xl border border-[#E8E5E180] bg-white p-6 ${cardShadow}`}
            >
              <header className="shrink-0">
                <p className="nova-text-label-base font-semibold text-[#242529]">
                  {plan.name}
                </p>
                
                <p className="mt-2 nova-text-h-xss text-[#242529]">
                  {plan.priceLine}
                </p>
                
                <p className="mt-1 nova-text-label-small-regular text-[#71717A]">
                  {plan.subtitle}
                </p>
                <div className="mt-4 h-[1px] bg-[#E8E5E180] mx-4" />
              </header>

              <div className="mt-4 flex min-h-0 flex-1 flex-col gap-5">
                {COMPARISON_ROWS.map((row) => (
                  <div key={row.label}>
                    <p className="nova-text-label-small text-[#242529]">
                      {row.label}
                    </p>
                    <div className="mt-1.5 flex items-center gap-2">
                      <MarkIcon
                        className="shrink-0"
                        alt=""
                        width={15}
                        height={15}
                        aria-hidden
                      />
                      <span className="nova-text-label-small-regular text-[#71717A]">
                        {row.values[colIndex]}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-6 h-[1px] bg-[#E8E5E180] mx-4" />

              <div className="mt-auto pt-6">
                <Button
                  variant={plan.ctaStyle === "muted" ? "outline" : "default"}
                  type="button"
                  disabled={plan.ctaStyle === "muted"}
                  className={plan.ctaStyle === "muted" ? "cursor-default disabled:opacity-100" : ""}
                >
                  {plan.cta}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
