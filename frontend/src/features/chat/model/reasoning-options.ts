export function getVisibleReasoningLevels(reasoningLevels: string[]) {
  return reasoningLevels.filter((level) => level !== "default");
}

export function getEffectiveReasoning(
  visibleReasoningLevels: string[],
  userSelectedReasoning: string | null,
) {
  if (userSelectedReasoning && visibleReasoningLevels.includes(userSelectedReasoning)) {
    return userSelectedReasoning;
  }

  return visibleReasoningLevels[0] ?? "";
}

export function getReasoningToSend(
  visibleReasoningLevels: string[],
  selectedReasoning: string,
) {
  return visibleReasoningLevels.includes(selectedReasoning)
    ? selectedReasoning
    : null;
}
