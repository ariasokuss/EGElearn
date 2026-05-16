type MainAppMobileGateVisibilityInput = {
  isPhone: boolean;
  isLoading: boolean;
};

export function shouldRenderMainAppChildren({
  isPhone,
  isLoading,
}: MainAppMobileGateVisibilityInput): boolean {
  return !isPhone && !isLoading;
}
