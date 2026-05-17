import { cn } from "@/shared/lib"

type PageCardProps = {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
}

export function PageCard({ children, className, style }: PageCardProps) {
  return (
    <div
      className={cn("overflow-hidden rounded-[18px] bg-white text-[var(--ege-text)]", className)}
      style={{
        boxShadow: "0px 18px 42px -32px rgba(11,15,26,0.35)",
        border: "1px solid var(--ege-border)",
        ...style,
      }}
    >
      {children}
    </div>
  )
}
