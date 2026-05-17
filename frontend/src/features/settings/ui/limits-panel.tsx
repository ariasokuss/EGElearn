"use client";

type UsageRowProps = {
  title: string;
  periodLabel: string;
  used: number;
  total: number;
  unit: string;
  remainingLabel: string;
};

function UsageRow({ title, periodLabel, used, total, unit, remainingLabel }: UsageRowProps) {
  const pct = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;
  return (
    <div className="border-b border-[#E8E5E180] py-5 last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="nova-text-label-small text-[#242529]">
            {title}
          </p>
          <p className="mt-1 nova-text-label-small-regular text-[#71717A]">
            {periodLabel}
          </p>
        </div>
        <div className="text-right">
          <p className="nova-text-label-small text-[#242529]">
            {used} / {total} {unit}
          </p>
          <p className="mt-1 nova-text-label-small-regular text-[#71717A]">
            {remainingLabel}
          </p>
        </div>
      </div>
      <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-[#F4F4F5]">
        <div
          className="h-full rounded-full bg-[#D3CCC8]"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function LimitsPanel() {
  return (
    <div className="mx-auto max-w-[720px] px-6 p-8">
      <div className="mt-8 rounded-2xl border border-[#E8E5E180] bg-white p-8 shadow-[0px_4px_6px_-1px_#0000000A,0px_2px_4px_-2px_#00000005]">
        <h1 className="nova-text-h-xss text-[#1D1B20]">
          Limits
        </h1>
        <div className="mt-4 h-px bg-[#E8E5E180]" />
        <UsageRow
          title="Chat messages"
          periodLabel="Months"
          used={224}
          total={1000}
          unit="messages"
          remainingLabel="776 messages remaining"
        />
        <UsageRow
          title="Test generations"
          periodLabel="Months"
          used={47}
          total={200}
          unit="tests"
          remainingLabel="153 tests remaining"
        />
      </div>
    </div>
  );
}
