/**
 * Heuristic: typical smartphone vs tablet/desktop.
 * Pass `maxTouchPoints` and `platform` on the client to reduce false positives
 * (e.g. iPad in desktop UA mode is not a phone).
 */
export function detectIsPhoneUserAgent(
  ua: string,
  maxTouchPoints?: number,
  platform?: string,
): boolean {
  if (!ua) return false;

  if (/iPad|PlayBook|Kindle|Silk/i.test(ua)) return false;
  if (/Nexus 7|Nexus 10|SM-T[0-9]+|GT-P[0-9]+/i.test(ua)) return false;

  if (/iPhone|iPod/i.test(ua)) return true;

  // iPadOS 13+ may report "Macintosh" with touch; not a phone.
  const touch = maxTouchPoints ?? 0;
  if ((platform === "MacIntel" || /Macintosh/i.test(ua)) && touch > 1 && !/iPhone|iPod/i.test(ua)) {
    return false;
  }

  if (/Android/i.test(ua)) {
    return /Mobile/i.test(ua);
  }

  if (/webOS|BlackBerry|BB10|IEMobile|Opera Mini/i.test(ua)) return true;

  return false;
}
