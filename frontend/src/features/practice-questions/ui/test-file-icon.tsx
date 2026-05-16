/**
 * TestFileIcon — document icon with checkmark, matching Figma test history cards.
 * Simplified from the original SVG for React compatibility.
 */
export function TestFileIcon({ className }: { className?: string }) {
  return (
    <svg
      width="56"
      height="68"
      viewBox="0 0 56 68"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* Document body */}
      <rect
        x="5"
        y="2"
        width="46"
        height="62"
        rx="8"
        fill="white"
        stroke="#E4E4E7"
        strokeOpacity="0.42"
        strokeWidth="0.8"
      />
      {/* Folded corner */}
      <path
        d="M37 2V14C37 16.2091 38.7909 18 41 18H51"
        stroke="#E4E4E7"
        strokeOpacity="0.42"
        strokeWidth="0.8"
      />
      {/* Checkmark */}
      <path
        d="M16 16L19.5 19.5L26 12"
        stroke="#E4E4E7"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Text lines */}
      <rect x="15" y="30" width="16" height="3" rx="1.5" fill="#E4E4E7" />
      <rect x="15" y="35" width="20" height="3" rx="1.5" fill="#F4F4F5" />
      <rect x="15" y="40" width="12" height="3" rx="1.5" fill="#F4F4F5" />
    </svg>
  )
}
