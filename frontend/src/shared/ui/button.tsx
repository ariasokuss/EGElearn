import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"
import { cn } from "@/shared/lib"
import { LoaderIcon } from "../assets/icons"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 p-1 items-center justify-center bg-clip-padding text-[var(--ege-text)] whitespace-nowrap transition-all outline-none select-none ring-transparent focus-visible:ring focus-visible:ring-[var(--ege-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--ege-canvas)] active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-[var(--ege-accent)] text-white hover:bg-[var(--ege-accent-strong)]",
        outline: "border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] hover:bg-[var(--ege-surface)] nova-shadow-sm",
        plain: "hover:bg-[var(--ege-surface)]",
      },
      size: {
        xxs: "h-5 px-2 nova-text-button-xxs",
        xs: "h-6 px-2 nova-text-label-tiny",
        sm: "h-7 px-2 nova-text-label-small",
        base: "h-8 px-2.5 nova-text-label-small",
        l: "h-9 px-3 nova-text-label-small",
        xl: "h-10 px-4 nova-text-label-base",
      },
      iconOnly: {
        true: "aspect-square overflow-hidden",
        false: ""
      },
      rounded: {
        true: "rounded-full",
        false: "rounded-[8px]"
      }
    },

    defaultVariants: {
      variant: "default",
      size: "base",
      iconOnly: false,
      rounded: true
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "base",
  iconOnly = false,
  rounded = true,
  asChild = false,
  isLoading,
  children,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean,
    isLoading?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"
  const loader = isLoading ? (
    <div className="absolute z-10 inset-0 flex justify-center items-center">
      <LoaderIcon className="animate-spin" />
    </div>
  ) : null
  const content =
    asChild && isLoading && React.isValidElement<{ children?: React.ReactNode }>(children)
      ? React.cloneElement(children, undefined, loader, children.props.children)
      : (
        <>
          {loader}
          {children}
        </>
      )

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(isLoading && "relative", buttonVariants({ variant, size, className, iconOnly, rounded }), isLoading && "*:not-first:invisible text-transparent")}
      {...props}
    >
      {content}
    </Comp>
  )
}

export type ButtonProps = React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  };

export type ButtonVariant = NonNullable<VariantProps<typeof buttonVariants>["variant"]>;
export type ButtonSize = NonNullable<VariantProps<typeof buttonVariants>["size"]>;

export { Button, buttonVariants }
