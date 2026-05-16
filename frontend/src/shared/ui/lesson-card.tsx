import { cn } from "@/shared/lib";

type LessonCardProps = {
  children: React.ReactNode;
  className?: string;
};

export function LessonCard({ children, className }: LessonCardProps) {
  return (
    <div
      className={cn(
        "rounded-[17px] border border-[#E4E4E76B] backdrop-blur-xs text-[#3F3F46]",
        className,
      )}
    >
      {children}
    </div>
  );
}
