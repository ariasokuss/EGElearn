import { LoginForm } from "@/features/auth";

export function AuthPage() {
  return (
    <section className="flex w-full max-w-[402px] flex-col gap-10">
      <h1 className="text-center nova-text-h-small-sb text-[#242529]">
        Log in
      </h1>
      <LoginForm />
    </section>
  );
}
