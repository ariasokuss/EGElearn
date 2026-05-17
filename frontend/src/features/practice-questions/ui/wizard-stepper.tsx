"use client"

import { cn } from "@/shared/lib"
import { WIZARD_STEPS } from "../lib"
import { Button } from "@/shared"
import { ArrowsPointingInIcon, ArrowsPointingOutIcon, XMarkIcon } from "@/shared/assets/icons"

type WizardStepperProps = {
  currentStep: number
  onBack?: VoidFunction
  onNext?: VoidFunction
  nextLabel?: string
  nextDisabled?: boolean
  isFullscreen?: boolean
  onToggleFullscreen?: VoidFunction
  onClose?: VoidFunction
}

export function WizardStepper({
  currentStep,
  onBack,
  onNext,
  nextLabel = "Подтвердить",
  nextDisabled = false,
  isFullscreen,
  onToggleFullscreen,
  onClose,
}: WizardStepperProps) {
  return (
    <div
      className={cn(
        "grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-[#F4F4F5]",
        isFullscreen ? "pt-4 pb-2" : "py-3",
      )}
    >
      <div className="flex items-center justify-self-start">
        {onClose && (
          <Button
            iconOnly
            size="sm"
            variant="plain"
            rounded={false}
            type="button"
            onClick={onClose}
            className="flex items-center justify-center text-[#71717A] hover:text-[#242529]"
          >
            <XMarkIcon className="size-4.5" />
          </Button>
        )}
        {onToggleFullscreen && (
          <Button
            iconOnly
            size="sm"
            variant="plain"
            rounded={false}
            type="button"
            onClick={onToggleFullscreen}
            className="flex items-center justify-center text-[#71717A] hover:text-[#242529]"
            aria-label={isFullscreen ? "Выйти из полноэкранного режима" : "На весь экран"}
            title={isFullscreen ? "Выйти из полноэкранного режима" : "На весь экран"}
          >
            {isFullscreen ? (
              <ArrowsPointingInIcon />
            ) : (
              <ArrowsPointingOutIcon />
            )}
          </Button>
        )}
      </div>

      {/* Steps indicator — centered, horizontally scrollable on small screens */}
      <div className="no-scrollbar min-w-0 overflow-x-auto">
        <div className="flex w-max mx-auto items-center gap-1 whitespace-nowrap">
          {WIZARD_STEPS.map((step, i) => (
            <div key={step.number} className="flex items-center gap-1">
              {i > 0 && (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="mx-0.5 text-[#71717A]">
                  <path d="M6 4L10 8L6 12" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
              <span
                className={cn(
                  "rounded-full px-3.5 py-1 nova-text-label-small transition-colors",
                  step.number === currentStep
                    ? "bg-[#F1ECE9] text-[#242529]"
                    : step.number < currentStep
                      ? "text-[#242529]"
                      : "text-[#A1A1AA] border border-[rgba(228,228,231,0.50)]",
                )}
                style={
                  step.number !== currentStep && step.number >= currentStep
                    ? { borderRadius: "var(--Border-Radius-rounded-full, 9999px)", color: "#242529" }
                    : undefined
                }
              >
                {step.number}. {step.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Navigation buttons */}
      <div className="flex items-center justify-end gap-2 justify-self-end">
        {onBack && (
          <Button
            size="sm"
            variant="plain"
            type="button"
            onClick={onBack}
            className="flex items-center gap-1 text-[#71717A] hover:text-[#242529]"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Назад
          </Button>
        )}
        {onNext && (
          <Button
            size="sm"
            type="button"
            onClick={onNext}
            disabled={nextDisabled}
            className="flex items-center gap-1 disabled:cursor-not-allowed"
          >
            {nextLabel}
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M6 4L10 8L6 12" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Button>
        )}
      </div>
    </div>
  )
}
