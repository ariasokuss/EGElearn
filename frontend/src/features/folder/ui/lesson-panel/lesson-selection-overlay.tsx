"use client";

import { memo } from "react";

import type { LessonSelectionState } from "./use-lesson-selection";

type OverlayProps = {
  selection: LessonSelectionState;
  handlesOnly?: boolean;
};

function HandlePin({ flipped, clipId }: { flipped?: boolean; clipId: string }) {
  return (
    <svg
      width="8"
      height="26"
      viewBox="0 0 8 26"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={flipped ? { transform: "rotate(180deg)" } : undefined}
    >
      <g clipPath={`url(#${clipId})`}>
        <path
          d="M3 5H4.9958C4.99812 5 5 5.00188 5 5.0042V25C5 25.5523 4.55228 26 4 26C3.44772 26 3 25.5523 3 25V5Z"
          fill="#C0ADA1"
        />
      </g>
      <circle cx="4" cy="3" r="3" fill="#C0ADA1" />
      <defs>
        <clipPath id={clipId}>
          <path
            d="M3 5H5V25C5 25.5523 4.55228 26 4 26C3.44772 26 3 25.5523 3 25V5Z"
            fill="white"
          />
        </clipPath>
      </defs>
    </svg>
  );
}

export const LessonSelectionOverlay = memo(function LessonSelectionOverlay({
  selection,
  handlesOnly,
}: OverlayProps) {
  const rects = selection.containerRects;
  if (rects.length === 0) return null;

  const first = rects[0];
  const last = rects[rects.length - 1];

  return (
    <>
      {!handlesOnly && (
        <div
          className="pointer-events-none absolute inset-0"
          style={{ mixBlendMode: "darken" }}
          aria-hidden="true"
        >
          {rects.map((r, i) => (
            <div
              key={i}
              className="absolute rounded-md bg-[#F1ECE9]"
              style={{
                top: r.top - 3,
                left: r.left - 1,
                width: r.width + 2,
                height: r.height + 7,
              }}
            />
          ))}
        </div>
      )}

      <div
        className="pointer-events-none absolute inset-0 z-10"
        aria-hidden="true"
      >
        <div
          className="absolute"
          style={{
            top: first.top - 6,
            left: first.left - 8,
          }}
        >
          <HandlePin clipId="lesson-handle-start" />
        </div>

        <div
          className="absolute"
          style={{
            top: last.bottom - 20,
            left: last.right,
          }}
        >
          <HandlePin clipId="lesson-handle-end" flipped />
        </div>
      </div>
    </>
  );
});
