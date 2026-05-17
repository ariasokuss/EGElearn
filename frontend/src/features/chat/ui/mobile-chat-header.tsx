"use client"

import { Button } from "@/shared"
import { PencilEditIcon, HideBarIcon } from "@/shared/assets/icons"

type MobileTab = "chat" | "history"

type MobileChatHeaderProps = {
  activeTab: MobileTab
  onTabChange: (tab: MobileTab) => void
  onNewChat: VoidFunction
  onCollapse?: VoidFunction
}

function HeaderIconButton({
  onClick,
  label,
  children,
}: {
  onClick: VoidFunction
  label: string
  children: React.ReactNode
}) {
  return (
    <Button
      variant="outline"
      iconOnly
      size="sm"
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex items-center justify-center"
    >
      <span className="flex h-4 w-4 items-center justify-center">{children}</span>
    </Button>
  )
}

function TabButton({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: VoidFunction
}) {
  return (
    <Button
      size="sm"
      type="button"
      onClick={onClick}
      className={[
        "flex items-center justify-center gap-1 duration-150",
        active
          ? "px-2 py-1"
          : "bg-transparent px-0 py-1 text-[var(--ege-muted)]",
      ].join(" ")}
    >
      {label}
    </Button>
  )
}

export function MobileChatHeader({
  activeTab,
  onTabChange,
  onNewChat,
  onCollapse,
}: MobileChatHeaderProps) {
  return (
    <div
      className="relative flex shrink-0 items-center justify-between bg-[var(--ege-surface-raised)] px-3 py-3"
      style={{ borderBottom: "1px solid var(--ege-border)" }}
    >
      {/* Tabs — always show both */}
      <div className="flex items-center gap-3">
        <TabButton
          label="Чат"
          active={activeTab === "chat"}
          onClick={() => onTabChange("chat")}
        />
        <TabButton
          label="История"
          active={activeTab === "history"}
          onClick={() => onTabChange("history")}
        />
      </div>

      {/* Icon buttons */}
      <div className="flex items-center gap-2">
        <HeaderIconButton onClick={onNewChat} label="Новый чат">
          <PencilEditIcon className="h-4 w-4" />
        </HeaderIconButton>
        {onCollapse && (
          <HeaderIconButton onClick={onCollapse} label="Свернуть панель">
            <HideBarIcon className="h-4 w-4" />
          </HeaderIconButton>
        )}
      </div>
    </div>
  )
}
