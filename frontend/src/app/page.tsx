import type { Metadata } from "next";
import "@/features/landing/landing-import.css";
import { headers } from "next/headers";
import { HomeRoute } from "@/features/landing";
import { buildPageMetadata, detectIsPhoneUserAgent } from "@/shared/lib";

export async function generateMetadata(): Promise<Metadata> {
  return buildPageMetadata({
    title: "NovaLearn — подготовка к ЕГЭ по предметам",
    description:
      "Готовься к ЕГЭ по русскому языку, математике, информатике и другим предметам: уроки, практика, прогресс и разбор ошибок.",
    path: "/",
    indexable: true,
  });
}

export default async function Page() {
  const ua = (await headers()).get("user-agent") ?? "";
  const isPhoneFromUa = detectIsPhoneUserAgent(ua);

  return <HomeRoute isPhoneFromUa={isPhoneFromUa} />;
}
