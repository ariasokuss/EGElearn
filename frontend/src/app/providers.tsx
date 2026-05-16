"use client";

import { AuthProvider } from "@/features/auth";
import { ReferralTracker } from "@/features/referral/ui/referral-tracker";
import { ThemeProvider } from "@/shared/lib/theme-provider";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ReferralTracker />
        {children}
      </AuthProvider>
    </ThemeProvider>
  );
}
