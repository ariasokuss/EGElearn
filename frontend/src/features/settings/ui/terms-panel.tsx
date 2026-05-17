"use client";

const cardShadow =
  "shadow-[0px_4px_6px_-1px_#0000000A,0px_2px_4px_-2px_#00000005]";

export function TermsPanel() {
  return (
    <div className="mx-auto max-w-[720px] px-6 py-8">
      <div
        className={`mt-8 rounded-2xl border border-[#E8E5E180] bg-white pt-[16px] px-[20px] pb-6 ${cardShadow}`}
      >
        <h1 className="nova-text-h-xss text-[#1D1B20]">
          Terms & Privacy
        </h1>

        <div className="mt-6 border-t border-[#E8E5E180]">
          <section className="py-4">
            <h2 className="nova-text-label-medium text-[#242529]">
              Terms of Service
            </h2>
            <p className="mt-1 nova-text-p-base text-[#71717A]">
              Conditions for accessing and using the product, subscriptions, and acceptable use.
            </p>
          </section>
          <section className="pt-2">
            <h2 className="nova-text-label-medium text-[#242529]">
              Privacy Policy
            </h2>
            <p className="mt-1 nova-text-p-base text-[#71717A]">
              How we collect, store, and process personal data and your choices.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
