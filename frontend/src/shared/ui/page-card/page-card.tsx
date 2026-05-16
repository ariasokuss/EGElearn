import { cn } from "@/shared/lib"

type PageCardProps = {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
}

export function PageCard({ children, className, style }: PageCardProps) {
  return (
    <div
      className={cn("overflow-hidden rounded-[15px] bg-[var(--ege-surface-raised)] text-[var(--ege-text)]", className)}
      style={{
        boxShadow: "0px 4px 6px -1px rgba(0,0,0,0.10), 0px 2px 4px -2px rgba(0,0,0,0.08)",
        border: "1px solid var(--ege-border)",
        ...style,
      }}
    >
      {children}
    </div>
  )
}
