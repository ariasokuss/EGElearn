"use client";

import { AuthProvider } from "@/features/auth";
import { ReferralTracker } from "@/features/referral/ui/referral-tracker";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <ReferralTracker />
      {children}
    </AuthProvider>
  );
}
