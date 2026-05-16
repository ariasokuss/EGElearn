import { ResetPasswordForm } from "@/features/auth";

interface ResetPageProps {
  token: string;
}

export function ResetPage({ token }: ResetPageProps) {
  return (
    <section className="flex w-full max-w-[402px] flex-col">
      <ResetPasswordForm token={token} />
    </section>
  );
}
