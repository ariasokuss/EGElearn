import type { ConversationSummary } from "@/entities/chat"

export type DateGroup = {
  label: string
  items: ConversationSummary[]
}

const GROUP_ORDER = ["Today", "Yesterday", "This Week", "This Month", "Older"] as const

function getGroupLabel(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()

  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startOfYesterday = new Date(startOfToday)
  startOfYesterday.setDate(startOfYesterday.getDate() - 1)

  // Start of week (Monday)
  const startOfWeek = new Date(startOfToday)
  const dayOfWeek = startOfToday.getDay()
  const daysFromMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1
  startOfWeek.setDate(startOfWeek.getDate() - daysFromMonday)

  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1)

  if (date >= startOfToday) return "Today"
  if (date >= startOfYesterday) return "Yesterday"
  if (date >= startOfWeek) return "This Week"
  if (date >= startOfMonth) return "This Month"
  return "Older"
}

export function groupConversations(conversations: ConversationSummary[]): DateGroup[] {
  const map = new Map<string, ConversationSummary[]>()

  for (const conv of conversations) {
    const dateStr = conv.updated_at || conv.created_at
    const label = getGroupLabel(dateStr)
    const list = map.get(label) ?? []
    list.push(conv)
    map.set(label, list)
  }

  // Return groups in the fixed display order, skipping empty groups
  return GROUP_ORDER.filter((label) => map.has(label)).map((label) => ({
    label,
    items: map.get(label)!,
  }))
}

export function formatConversationDate(dateStr: string): string {
  const date = new Date(dateStr)
  const day = date.getDate()
  const month = date.toLocaleString("en-US", { month: "long" })
  return `${day} ${month}`
}
