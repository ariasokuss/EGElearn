"use client";

type ActivityEventPayload = {
  event_type: "chat_opened";
  route_label?: string;
  entity_type?: string;
  entity_id?: string;
  folder_id?: string;
  lesson_id?: string;
  metadata?: Record<string, unknown>;
};

export function recordActivityEvent(payload: ActivityEventPayload): void {
  if (typeof window === "undefined") return;

  void fetch("/api/v1/activity/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    keepalive: true,
    body: JSON.stringify(payload),
  }).catch(() => {
    // Activity logging must never interrupt the learning flow.
  });
}
