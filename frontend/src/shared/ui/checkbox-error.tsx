import CheckboxIcon from "@/shared/assets/icons/checkbox.svg";
import XMarkIcon from "@/shared/assets/icons/x-mark.svg";

import { cn } from "@/shared/lib";

type CheckboxErrorProps = {
  className?: string;
  color?: string;
  iconColor?: string;
};

export function CheckboxError({
  className,
  color = "#C77785",
  iconColor = "white",
}: CheckboxErrorProps) {
  return (
    <div className={cn("relative h-5 w-5 shrink-0", className)}>
      <CheckboxIcon className="absolute inset-0 h-5 w-5" />
      <div className="absolute h-5 w-5 rounded-full" style={{ background: color }} />
      <XMarkIcon className="absolute inset-0 m-auto [&_path]:stroke-(--icon-color)" style={{ "--icon-color": iconColor } as React.CSSProperties} />
    </div>
  );
}
