import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";
import { ChatView } from "@/views/chat";

export const metadata: Metadata = buildPageMetadata({
  title: "Chat",
  description: "Private NovaLearn chat workspace.",
  path: "/chat",
  indexable: false,
});

export default function ChatPage() {
  return <ChatView />;
}
