import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";
import { ChatView } from "@/views/chat";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;

  return buildPageMetadata({
    title: "Chat Session",
    description: "Private NovaLearn conversation session.",
    path: `/chat/${id}`,
    indexable: false,
  });
}

type Props = {
  params: Promise<{ id: string }>;
};

export default async function ChatPage({ params }: Props) {
  const { id } = await params;
  return <ChatView initialConversationId={id} />;
}
