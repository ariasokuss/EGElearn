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
        "group/calendar w-[242px] rounded-[20px] border border-[#0000000D] bg-white p-4 [--cell-radius:8px] [--cell-size:--spacing(7)] shadow-[0px_8px_16px_-4px_#0000000A,0px_4px_8px_-2px_#00000008,0px_2px_4px_-1px_#00000005,0px_1px_2px_0px_#00000003]",
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
          "absolute inset-0 bg-white opacity-0",
          defaultClassNames.dropdown,
        ),
        caption_label: cn(
          "nova-text-label-small text-[#242529] select-none",
          captionLayout === "label"
            ? ""
            : "flex items-center gap-1 rounded-(--cell-radius) [&>svg]:size-3.5 [&>svg]:text-[#72706F]",
          defaultClassNames.caption_label,
        ),
        table: "w-full border-collapse",
        weekdays: cn("flex gap-0.5 mb-1.5", defaultClassNames.weekdays),
        weekday: cn(
          "flex items-center justify-center flex-1 w-[28px] h-[24px] rounded-(--cell-radius) nova-text-label-tiny text-[#A1A1AA] select-none",
          defaultClassNames.weekday,
        ),
        week: cn("mt-0.5 flex w-full gap-0.5", defaultClassNames.week),
        week_number_header: cn(
          "w-(--cell-size) select-none",
          defaultClassNames.week_number_header,
        ),
        week_number: cn(
          "text-[0.8rem] text-[#72706F] select-none",
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
          "relative isolate z-0 rounded-l-(--cell-radius) bg-[#F1ECE9] after:absolute after:inset-y-0 after:right-0 after:w-4 after:bg-[#F1ECE9]",
          defaultClassNames.range_start,
        ),
        range_middle: cn("rounded-none", defaultClassNames.range_middle),
        range_end: cn(
          "relative isolate z-0 rounded-r-(--cell-radius) bg-[#F1ECE9] after:absolute after:inset-y-0 after:left-0 after:w-4 after:bg-[#F1ECE9]",
          defaultClassNames.range_end,
        ),
        today: cn(
          "rounded-(--cell-radius) bg-[#F1ECE9] text-[#242529] data-[selected=true]:rounded-none",
          defaultClassNames.today,
        ),
        outside: cn(
          "text-[#A1A1AA] aria-selected:text-[#A1A1AA]",
          defaultClassNames.outside,
        ),
        disabled: cn("text-[#72706F] opacity-50", defaultClassNames.disabled),
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
              <div className="flex items-center justify-center rounded-full h-7 w-7 shrink-0 transition-all duration-150 hover:bg-[#F0EFED] active:bg-[#E8E5E1]">
                <ChevronLeftIcon
                  className={cn("cn-rtl-flip size-4", className)}
                  {...props}
                />
              </div>
            );
          }

          if (orientation === "right") {
            return (
              <div className="flex items-center justify-center rounded-full h-7 w-7 shrink-0 transition-all duration-150 hover:bg-[#F0EFED] active:bg-[#E8E5E1]">
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
        "relative isolate z-10 flex aspect-square size-auto w-full min-w-(--cell-size) flex-col gap-1 border-0 nova-text-label-tiny hover:bg-[#F1ECE9] group-data-[focused=true]/day:relative group-data-[focused=true]/day:z-10 group-data-[focused=true]/day:border-[#242529] group-data-[focused=true]/day:ring-[3px] group-data-[focused=true]/day:ring-[#24252940] data-[range-end=true]:rounded-(--cell-radius) data-[range-end=true]:rounded-r-(--cell-radius) data-[range-end=true]:bg-[#242529] data-[range-end=true]:text-white data-[range-middle=true]:rounded-none data-[range-middle=true]:bg-[#F1ECE9] data-[range-middle=true]:text-[#242529] data-[range-start=true]:rounded-(--cell-radius) data-[range-start=true]:rounded-l-(--cell-radius) data-[range-start=true]:bg-[#242529] data-[range-start=true]:text-white data-[selected-single=true]:bg-[#E8E5E1] data-[selected-single=true]:text-[#242529] [&>span]:text-xs [&>span]:opacity-70 group/button shrink-0 items-center justify-center rounded-lg bg-clip-padding whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
        modifiers.outside ? "text-[#A1A1AA]" : "text-[#242529]",
        defaultClassNames.day,
        className
      )}
      {...props}
    />
  )
}

export { Calendar, CalendarDayButton }
