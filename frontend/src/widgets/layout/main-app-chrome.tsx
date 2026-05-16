import { FoldersProvider } from "@/features/home";
import { PaywallModalHost } from "@/features/paywall";
import { OnboardingPopup } from "@/features/onboarding-popup/ui/onboarding-popup";
import { TestGuardProvider } from "@/shared/lib";
import { Notifications } from "@/shared/ui";

import { AppLayout } from "./app-layout";
import { MainAppMobileGate } from "./main-app-mobile-gate";
import { MobileAppUnavailable } from "./mobile-app-unavailable";

type MainAppChromeProps = {
  children: React.ReactNode;
  isPhoneFromUa: boolean;
};

/** Shared shell for logged-in app routes: mobile gate, folders, sidebar layout, modals. */
export function MainAppChrome({ children, isPhoneFromUa }: MainAppChromeProps) {
  return (
    <MainAppMobileGate isPhoneFromUa={isPhoneFromUa} stub={<MobileAppUnavailable />}>
      <FoldersProvider>
        <TestGuardProvider>
          <AppLayout>{children}</AppLayout>
          <Notifications />
          <PaywallModalHost />
          <OnboardingPopup />
        </TestGuardProvider>
      </FoldersProvider>
    </MainAppMobileGate>
  );
}
