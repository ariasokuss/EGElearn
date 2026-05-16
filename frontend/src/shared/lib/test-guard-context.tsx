"use client"

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react"
import { Modal } from "@/shared/ui"

type TestGuardContextValue = {
  isTestActive: boolean
  activateGuard: () => void
  deactivateGuard: () => void
  requestNavigation: () => Promise<boolean>
}

const TestGuardContext = createContext<TestGuardContextValue | null>(null)

export function TestGuardProvider({ children }: { children: ReactNode }) {
  const [isTestActive, setIsTestActive] = useState(false)
  const resolveRef = useRef<((proceed: boolean) => void) | null>(null)
  const [showModal, setShowModal] = useState(false)

  const activateGuard = useCallback(() => setIsTestActive(true), [])
  const deactivateGuard = useCallback(() => setIsTestActive(false), [])

  const requestNavigation = useCallback((): Promise<boolean> => {
    if (!isTestActive) return Promise.resolve(true)
    return new Promise((resolve) => {
      resolveRef.current = resolve
      setShowModal(true)
    })
  }, [isTestActive])

  const handleConfirm = useCallback(() => {
    setShowModal(false)
    setIsTestActive(false)
    resolveRef.current?.(true)
    resolveRef.current = null
  }, [])

  const handleCancel = useCallback(() => {
    setShowModal(false)
    resolveRef.current?.(false)
    resolveRef.current = null
  }, [])

  return (
    <TestGuardContext.Provider value={{ isTestActive, activateGuard, deactivateGuard, requestNavigation }}>
      {children}
      <Modal
        title="Are you sure you want to exit this test?"
        description="Your progress will be saved and you will be able access it through test history."
        primaryButtonText="Confirm"
        secondaryButtonText="Cancel"
        isOpen={showModal}
        onPrimaryClick={handleConfirm}
        onSecondaryClick={handleCancel}
      />
    </TestGuardContext.Provider>
  )
}

export function useTestGuard() {
  const ctx = useContext(TestGuardContext)
  if (!ctx) {
    return {
      isTestActive: false,
      activateGuard: () => {},
      deactivateGuard: () => {},
      requestNavigation: () => Promise.resolve(true),
    }
  }
  return ctx
}
