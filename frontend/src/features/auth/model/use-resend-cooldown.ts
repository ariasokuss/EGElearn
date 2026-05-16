import { useCallback, useEffect, useState } from "react";

const DEFAULT_SECONDS = 60;

export function useResendCooldown(totalSeconds = DEFAULT_SECONDS) {
  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const id = window.setTimeout(() => {
      setSecondsLeft((s) => Math.max(0, s - 1));
    }, 1000);
    return () => window.clearTimeout(id);
  }, [secondsLeft]);

  const start = useCallback(
    (seconds = totalSeconds) => {
      setSecondsLeft(seconds);
    },
    [totalSeconds]
  );

  return {
    secondsLeft,
    isCoolingDown: secondsLeft > 0,
    start,
  };
}
