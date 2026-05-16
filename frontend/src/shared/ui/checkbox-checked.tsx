import CheckboxIcon from "@/shared/assets/icons/checkbox.svg";
import CheckedIcon from "@/shared/assets/icons/check.svg";

import { cn } from "@/shared/lib";

type CheckboxCheckedProps = {
  className?: string;
  color?: string;
  checkColor?: string;
};

export function CheckboxChecked({
  className,
  color = "#E8DFD9",
  checkColor = "#242529",
}: CheckboxCheckedProps) {
  return (
    <div className={cn("relative h-5 w-5 shrink-0", className)}>
      <CheckboxIcon className="absolute inset-0 h-5 w-5" />
      <div className="absolute h-5 w-5 rounded-full" style={{ background: color }} />
      <CheckedIcon className="absolute inset-0 m-auto size-3.5 [&_path]:stroke-(--check-color)" style={{ "--check-color": checkColor } as React.CSSProperties} />
    </div>
  );
}
