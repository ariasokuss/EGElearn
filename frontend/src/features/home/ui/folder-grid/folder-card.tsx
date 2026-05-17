import { cn } from "@/shared/lib";

type FolderCardProps = {
  onClick?: VoidFunction;
  pressed?: boolean;
  children: React.ReactNode;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
};

export function FolderCard({ onClick, pressed, children, dragHandleProps }: FolderCardProps) {
  return (
    <button
      {...dragHandleProps}
      onClick={onClick}
      className={cn(
        "group/card flex h-[164px] w-full min-w-[210px] shrink-0",
        "flex-col items-start justify-end rounded-[12px] p-0 text-left",
        "text-[#0b0f1a] transition-[transform,opacity] duration-300 ease-out",
        !pressed && "hover:-translate-y-0.5",
        !pressed && "active:translate-y-0 active:transition-none",
        pressed && "transition-none opacity-80",
      )}
    >
      {children}
    </button>
  );
}
