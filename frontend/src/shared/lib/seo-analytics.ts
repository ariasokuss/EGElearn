type SeoEventPayload = Record<string, string | number | boolean | null | undefined>;

export function trackSeoEvent(eventName: string, payload: SeoEventPayload = {}) {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(
    new CustomEvent("novalearn:seo-event", {
      detail: {
        eventName,
        ...payload,
      },
    }),
  );
}
