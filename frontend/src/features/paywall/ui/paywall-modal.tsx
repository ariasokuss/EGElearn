"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/shared";
import { cn } from "@/shared/lib";
import { MarkIcon, MenuUpgradeIcon, XMarkIcon } from "@/shared/assets/icons";

type PaywallPlan = {
  name: "Plus" | "Pro";
  priceLine: string;
  tagline: string;
  bullets: string[];
  recommended?: boolean;
};

const PLANS: PaywallPlan[] = [
  {
    name: "Plus",
    priceLine: "$12 / month",
    tagline: "More chats & tests for steady prep",
    bullets: [
      "300 chat messages per month",
      "All lesson topics unlocked",
      "3 Nova tests per subject",
    ],
    recommended: true,
  },
  {
    name: "Pro",
    priceLine: "$17 / month",
    tagline: "Everything you need for serious study",
    bullets: [
      "800 chat messages per month",
      "150 Feynman sessions per month",
      "Unlimited MyPastPapers",
    ],
  },
];

const cardShadow =
  "shadow-[0px_4px_6px_-1px_#0000000A,0px_2px_4px_-2px_#00000005]";

export type PaywallModalProps = {
  isOpen: boolean;
  onClose(): void;
};

export function PaywallModal({ isOpen, onClose }: PaywallModalProps) {
  const router = useRouter();

  const handleUpgrade = () => {
    router.push("/settings");
    onClose();
  };

  return (
    <div
      data-paywall-open={isOpen ? "true" : undefined}
      className={cn(
        "z-100 flex justify-center items-center inset-0 bg-black/50 transition-all fixed",
        isOpen ? "visible opacity-100" : "invisible opacity-0",
      )}
    >
      <div className="flex flex-col w-full max-w-200 bg-white border border-[#F4F4F5] rounded-[20px]">
        <div className="w-full p-1.5 border-b border-[#F4F4F5] flex justify-end">
          <Button
            iconOnly
            size="sm"
            variant="outline"
            className="flex justify-center items-center"
            onClick={onClose}
            aria-label="Close"
          >
            <XMarkIcon className="size-4" />
          </Button>
        </div>

        <div className="w-full p-1.5">
          <div className="flex flex-col gap-y-6 w-full p-8 rounded-[16px] nova-shadow-sm">
            <div className="flex flex-col items-center gap-y-3">
              <MenuUpgradeIcon className="size-8" />
              <p className="text-center nova-text-label-base text-[#242529]">
                NovaLearn is growing faster than our free tier can keep up
              </p>
              <p className="text-center nova-text-label-small text-[#71717A] max-w-100">
                Based on your activity we&apos;d recommend upgrading to Plus or
                Pro — keep your chats, tests and lessons flowing without limits.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {PLANS.map((plan) => (
                <div
                  key={plan.name}
                  className={cn(
                    "flex h-full min-h-0 flex-col rounded-2xl border border-[#E8E5E180] bg-white p-5",
                    cardShadow,
                    plan.recommended && "ring-1 ring-nova-200",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <p className="nova-text-label-base font-semibold text-[#242529]">
                      {plan.name}
                    </p>
                    {plan.recommended && (
                      <span className="nova-text-label-tiny text-[#242529] bg-nova-100 px-2 py-0.5 rounded-full">
                        Recommended
                      </span>
                    )}
                  </div>

                  <p className="mt-2 nova-text-h-xss text-[#242529]">
                    {plan.priceLine}
                  </p>
                  <p className="mt-1 nova-text-label-small-regular text-[#71717A]">
                    {plan.tagline}
                  </p>

                  <div className="my-4 h-[1px] bg-[#E8E5E180]" />

                  <ul className="flex flex-col gap-3">
                    {plan.bullets.map((b) => (
                      <li key={b} className="flex items-start gap-2">
                        <MarkIcon
                          className="shrink-0 mt-0.5"
                          alt=""
                          width={15}
                          height={15}
                          aria-hidden
                        />
                        <span className="nova-text-label-small-regular text-[#71717A]">
                          {b}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            <div className="flex justify-center gap-x-2 nova-text-label-small text-[#242529]">
              <Button onClick={handleUpgrade}>See plans</Button>
              <Button variant="plain" onClick={onClose}>
                Maybe later
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
