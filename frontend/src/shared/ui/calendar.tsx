"use client"

import * as React from "react"
import {
  DayPicker,
  getDefaultClassNames,
  type DayButton,
  type Locale,
} from "react-day-picker"

import { cn } from "../lib"
import { Button, buttonVariants } from "./button"
import { ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon } from "../assets/icons"

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  captionLayout = "label",
  buttonVariant = "plain",
  locale,
  formatters,
  components,
  ...props
}: React.ComponentProps<typeof DayPicker> & {
  buttonVariant?: React.ComponentProps<typeof Button>["variant"]
}) {
  const defaultClassNames = getDefaultClassNames()

  return (
    <DayPicker
      data-exam-panel
      showOutsideDays={showOutsideDays}
      className={cn(
        "group/calendar w-[242px] rounded-[20px] border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-4 text-[var(--ege-text)] [--cell-radius:8px] [--cell-size:--spacing(7)] shadow-[0px_8px_16px_-4px_rgba(0,0,0,0.18),0px_4px_8px_-2px_rgba(0,0,0,0.12)]",
        String.raw`rtl:**:[.rdp-button\_next>svg]:rotate-180`,
        String.raw`rtl:**:[.rdp-button\_previous>svg]:rotate-180`,
        className,
      )}
      captionLayout={captionLayout}
      locale={locale}
      formatters={{
        formatMonthDropdown: (date) =>
          date.toLocaleString(locale?.code, { month: "short" }),
        ...formatters,
      }}
      classNames={{
        root: cn("w-fit", defaultClassNames.root),
        months: cn(
          "relative flex flex-col gap-2 md:flex-row",
          defaultClassNames.months,
        ),
        month: cn("flex w-full flex-col gap-2", defaultClassNames.month),
        nav: cn(
          "absolute inset-x-0 top-0 flex w-full items-center justify-between gap-1",
          defaultClassNames.nav,
        ),
        button_previous: cn(
          buttonVariants({ variant: buttonVariant }),
          "size-(--cell-size) p-0 select-none aria-disabled:opacity-50",
          defaultClassNames.button_previous,
        ),
        button_next: cn(
          buttonVariants({ variant: buttonVariant }),
          "size-(--cell-size) p-0 select-none aria-disabled:opacity-50",
          defaultClassNames.button_next,
        ),
        month_caption: cn(
          "flex h-(--cell-size) w-full items-center justify-center px-(--cell-size)",
          defaultClassNames.month_caption,
        ),
        dropdowns: cn(
          "flex h-(--cell-size) w-full items-center justify-center gap-1.5 nova-text-label-medium",
          defaultClassNames.dropdowns,
        ),
        dropdown_root: cn(
          "relative rounded-(--cell-radius)",
          defaultClassNames.dropdown_root,
        ),
        dropdown: cn(
          "absolute inset-0 bg-[var(--ege-surface-raised)] opacity-0",
          defaultClassNames.dropdown,
        ),
        caption_label: cn(
          "nova-text-label-small text-[var(--ege-text)] select-none",
          captionLayout === "label"
            ? ""
            : "flex items-center gap-1 rounded-(--cell-radius) [&>svg]:size-3.5 [&>svg]:text-[var(--ege-muted)]",
          defaultClassNames.caption_label,
        ),
        table: "w-full border-collapse",
        weekdays: cn("flex gap-0.5 mb-1.5", defaultClassNames.weekdays),
        weekday: cn(
          "flex h-[24px] w-[28px] flex-1 items-center justify-center rounded-(--cell-radius) nova-text-label-tiny text-[var(--ege-muted)] select-none",
          defaultClassNames.weekday,
        ),
        week: cn("mt-0.5 flex w-full gap-0.5", defaultClassNames.week),
        week_number_header: cn(
          "w-(--cell-size) select-none",
          defaultClassNames.week_number_header,
        ),
        week_number: cn(
          "text-[0.8rem] text-[var(--ege-muted)] select-none",
          defaultClassNames.week_number,
        ),
        day: cn(
          "group/day relative aspect-square h-full w-full rounded-(--cell-radius) p-0 text-center select-none [&:last-child[data-selected=true]_button]:rounded-r-(--cell-radius)",
          props.showWeekNumber
            ? "[&:nth-child(2)[data-selected=true]_button]:rounded-l-(--cell-radius)"
            : "[&:first-child[data-selected=true]_button]:rounded-l-(--cell-radius)",
          defaultClassNames.day,
        ),
        range_start: cn(
          "relative isolate z-0 rounded-l-(--cell-radius) bg-[var(--ege-surface)] after:absolute after:inset-y-0 after:right-0 after:w-4 after:bg-[var(--ege-surface)]",
          defaultClassNames.range_start,
        ),
        range_middle: cn("rounded-none", defaultClassNames.range_middle),
        range_end: cn(
          "relative isolate z-0 rounded-r-(--cell-radius) bg-[var(--ege-surface)] after:absolute after:inset-y-0 after:left-0 after:w-4 after:bg-[var(--ege-surface)]",
          defaultClassNames.range_end,
        ),
        today: cn(
          "rounded-(--cell-radius) bg-[var(--ege-surface)] text-[var(--ege-text)] data-[selected=true]:rounded-none",
          defaultClassNames.today,
        ),
        outside: cn(
          "text-[var(--ege-muted)] aria-selected:text-[var(--ege-muted)]",
          defaultClassNames.outside,
        ),
        disabled: cn("text-[var(--ege-muted)] opacity-50", defaultClassNames.disabled),
        hidden: cn("invisible", defaultClassNames.hidden),
        ...classNames,
      }}
      components={{
        Root: ({ className, rootRef, ...props }) => {
          return (
            <div
              data-slot="calendar"
              ref={rootRef}
              className={cn(className)}
              {...props}
            />
          );
        },
        Chevron: ({ className, orientation, ...props }) => {
          if (orientation === "left") {
            return (
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-all duration-150 hover:bg-[var(--ege-surface)] active:bg-[var(--ege-track)]">
                <ChevronLeftIcon
                  className={cn("cn-rtl-flip size-4", className)}
                  {...props}
                />
              </div>
            );
          }

          if (orientation === "right") {
            return (
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-all duration-150 hover:bg-[var(--ege-surface)] active:bg-[var(--ege-track)]">
                <ChevronRightIcon
                  className={cn("cn-rtl-flip size-4", className)}
                  {...props}
                />
              </div>
            );
          }

          return (
            <ChevronDownIcon className={cn("size-4", className)} {...props} />
          );
        },
        DayButton: ({ ...props }) => (
          <CalendarDayButton locale={locale} {...props} />
        ),
        WeekNumber: ({ children, ...props }) => {
          return (
            <td {...props}>
              <div className="flex size-(--cell-size) items-center justify-center text-center">
                {children}
              </div>
            </td>
          );
        },
        ...components,
      }}
      {...props}
    />
  );
}

function CalendarDayButton({
  className,
  day,
  modifiers,
  locale,
  ...props
}: React.ComponentProps<typeof DayButton> & { locale?: Partial<Locale> }) {
  const defaultClassNames = getDefaultClassNames()

  const ref = React.useRef<HTMLButtonElement>(null)
  React.useEffect(() => {
    if (modifiers.focused) ref.current?.focus()
  }, [modifiers.focused])

  return (
    <button
      ref={ref}
      data-day={day.date.toLocaleDateString(locale?.code)}
      data-selected-single={
        modifiers.selected &&
        !modifiers.range_start &&
        !modifiers.range_end &&
        !modifiers.range_middle
      }
      data-range-start={modifiers.range_start}
      data-range-end={modifiers.range_end}
      data-range-middle={modifiers.range_middle}
      className={cn(
        "group/button relative isolate z-10 flex aspect-square size-auto w-full min-w-(--cell-size) shrink-0 flex-col items-center justify-center gap-1 rounded-lg border-0 bg-clip-padding nova-text-label-tiny whitespace-nowrap outline-none transition-all select-none hover:bg-[var(--ege-surface)] active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 group-data-[focused=true]/day:relative group-data-[focused=true]/day:z-10 group-data-[focused=true]/day:ring-[3px] group-data-[focused=true]/day:ring-[var(--ege-track)] data-[range-end=true]:rounded-(--cell-radius) data-[range-end=true]:rounded-r-(--cell-radius) data-[range-end=true]:bg-[var(--ege-accent)] data-[range-end=true]:text-white data-[range-middle=true]:rounded-none data-[range-middle=true]:bg-[var(--ege-surface)] data-[range-middle=true]:text-[var(--ege-text)] data-[range-start=true]:rounded-(--cell-radius) data-[range-start=true]:rounded-l-(--cell-radius) data-[range-start=true]:bg-[var(--ege-accent)] data-[range-start=true]:text-white data-[selected-single=true]:bg-[var(--ege-accent)] data-[selected-single=true]:text-white [&>span]:text-xs [&>span]:opacity-70",
        modifiers.outside ? "text-[var(--ege-muted)]" : "text-[var(--ege-text)]",
        defaultClassNames.day,
        className
      )}
      {...props}
    />
  )
}

export { Calendar, CalendarDayButton }
