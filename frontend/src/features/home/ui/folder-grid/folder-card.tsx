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
        "group/card flex h-[138px] w-[230px] shrink-0",
        "flex-col rounded-[18px] p-4 text-left",
        "border text-[var(--ege-text)]",
        !pressed && "bg-[var(--ege-surface-raised)] border-[var(--ege-border)] transition-[background-color,box-shadow,border-color] duration-300 ease-out",
        !pressed && "hover:border-[var(--ege-accent)] hover:shadow-[0px_2px_8px_0px_rgba(11,15,26,0.12)]",
        !pressed && "active:transition-none active:bg-[var(--ege-surface)] active:border-[var(--ege-accent)]",
        pressed && "transition-none bg-[var(--ege-surface)] border-[var(--ege-accent)] shadow-[0px_0px_0px_3px_rgba(217,16,36,0.16)]",
      )}
    >
      {children}
    </button>
  );
}
