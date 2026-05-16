"use client";

import { usePaywall } from "../model/use-paywall";
import { PaywallModal } from "./paywall-modal";

export function PaywallModalHost() {
  const { isOpen, close } = usePaywall();
  return <PaywallModal isOpen={isOpen} onClose={close} />;
}
