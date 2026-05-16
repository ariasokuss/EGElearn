import { cn } from "@/shared/lib";

type FolderIconProps = {
  className?: string;
  pressed?: boolean;
};

export function FolderIcon({ className, pressed }: FolderIconProps) {
  return (
    <svg
      width="96"
      height="75"
      viewBox="0 0 96 75"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("h-[70px] w-[90px]", className)}
    >
      <g opacity={pressed ? "1" : "0.9"}>
        <path
          d="M12 0.464844H80.9512C87.3217 0.464844 92.4863 5.6295 92.4863 12V62.4727C92.4863 68.8432 87.3217 74.0078 80.9512 74.0078H12C5.6295 74.0078 0.464844 68.8432 0.464844 62.4727V12C0.464844 5.6295 5.6295 0.464844 12 0.464844Z"
          fill="var(--ege-surface)"
          className="transition-colors group-hover/card:fill-[var(--ege-track)]"
        />
        <path
          d="M12 0.464844H80.9512C87.3217 0.464844 92.4863 5.6295 92.4863 12V62.4727C92.4863 68.8432 87.3217 74.0078 80.9512 74.0078H12C5.6295 74.0078 0.464844 68.8432 0.464844 62.4727V12C0.464844 5.6295 5.6295 0.464844 12 0.464844Z"
          stroke="var(--ege-border)"
          strokeWidth="0.930392"
        />
        <path
          d="M10 7.48828H33.7588C38.0181 7.48828 42.221 8.46588 46.043 10.3457L55.2773 14.8877C57.1769 15.8219 59.266 16.3076 61.3828 16.3076H84C90.3512 16.3076 95.4999 21.4564 95.5 27.8076V62.4727C95.5 68.8239 90.3513 73.9727 84 73.9727H10C4.7533 73.9727 0.5 69.7194 0.5 64.4727V16.9883C0.5 11.7416 4.7533 7.48828 10 7.48828Z"
          fill="var(--ege-surface-raised)"
          className={cn(
            "transition-colors group-hover/card:fill-[var(--ege-surface)]",
            pressed && "fill-[var(--ege-surface)]",
          )}
          stroke="var(--ege-border)"
        />
      </g>
    </svg>
  );
}
