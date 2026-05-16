import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { buildPageMetadata } from "@/shared/lib";
import { ResetPage } from "@/views/restore";

export const metadata: Metadata = buildPageMetadata({
  title: "Set New Password",
  description: "Set a new password for your NovaLearn account.",
  path: "/restore/reset",
  indexable: false,
});

export default async function ResetPassword({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const params = await searchParams;
  const token = params.token ?? "";

  if (!token) {
    redirect("/restore");
  }

  return <ResetPage token={token} />;
}
