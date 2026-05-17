type OnboardingDismissState = {
  watchedVideoFully: boolean;
};

export type OnboardingDismissAction = "close";

export function getOnboardingDismissAction(
  state: OnboardingDismissState,
): OnboardingDismissAction {
  void state.watchedVideoFully;
  return "close";
}
