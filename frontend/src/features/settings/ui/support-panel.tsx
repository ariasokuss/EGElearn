"use client";

import { useAuth } from "@/features/auth";
import { Button } from "@/shared";

const cardShadow =
  "shadow-[0px_4px_6px_-1px_#0000000A,0px_2px_4px_-2px_#00000005]";

export function SupportPanel() {
  const { user } = useAuth();
  const email = user?.email ?? "your email";

  return (
    <div className="mx-auto max-w-[760px] px-6 py-8">
      <div
        className={`mt-8 rounded-3xl border border-[#E8E5E180] bg-white p-8 ${cardShadow}`}
      >
        <h1 className="nova-text-h-xss text-[#242529]">
          Describe your problem
        </h1>
        <div className="mt-4 h-px w-full bg-[#E8E5E180]" />

        <p className="mt-6 nova-text-p-base text-[#000000]/68">
          The Nova Learn team will get back to you via the email provided during registration within
          48 hours. Your email address for the response will be:{" "}
          <strong className="font-medium text-[#242529]">{email}</strong>
        </p>

        <div className="mt-8 flex flex-col gap-6">
          <input
            type="text"
            name="problem-title"
            autoComplete="off"
            className="h-12 w-full rounded-full border border-[#E8E5E1] bg-white px-5 nova-text-label-small text-[#242529] transition-shadow placeholder:text-[#71717A]"
            placeholder="Problem title"
          />

          <div className="flex min-h-[200px] flex-col rounded-2xl border border-[#E8E5E1] p-4">
            <textarea
              name="message"
              rows={5}
              className="min-h-[120px] w-full flex-1 resize-none border-0 bg-transparent nova-text-label-small text-[#242529] outline-none ring-0 placeholder:text-[#71717A] focus-visible:ring-0"
              placeholder="Write your answer..."
            />
            <Button
              size="l"
              type="button"
              className="mt-4 self-start"
            >
              Send message
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
