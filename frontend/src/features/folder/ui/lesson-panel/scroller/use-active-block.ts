import { useEffect, useRef, useState, type RefObject } from "react";

export function useActiveBlock(
  scrollRef: RefObject<HTMLElement | null>,
  blockIds: string[],
): string | null {
  const [activeId, setActiveId] = useState<string | null>(
    blockIds[0] ?? null,
  );
  const rafRef = useRef(0);

  useEffect(() => {
    const root = scrollRef.current;
    if (!root || blockIds.length === 0) return;

    const elements = blockIds
      .map((id) => root.querySelector<HTMLElement>(`[data-block-id="${id}"]`))
      .filter(Boolean) as HTMLElement[];

    if (elements.length === 0) return;

    const update = () => {
      const rootTop = root.getBoundingClientRect().top;
      const targetY = rootTop + root.clientHeight * 0.25;
      const atBottom =
        root.scrollHeight - root.scrollTop - root.clientHeight < 2;

      const atTop = root.scrollTop < 50;

      if (atTop) {
        setActiveId(elements[0]?.dataset.blockId ?? null);
        return;
      }

      let candidate: string | null = null;

      for (const el of elements) {
        if (el.getBoundingClientRect().top <= targetY) {
          candidate = el.dataset.blockId ?? null;
        }
      }

      if (atBottom) {
        const viewportBottom = rootTop + root.clientHeight;
        for (const el of elements) {
          if (el.getBoundingClientRect().top < viewportBottom) {
            candidate = el.dataset.blockId ?? null;
          }
        }
      }

      if (candidate) setActiveId(candidate);
    };

    const handleScroll = () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(update);
    };

    root.addEventListener("scroll", handleScroll, { passive: true });
    update();

    return () => {
      root.removeEventListener("scroll", handleScroll);
      cancelAnimationFrame(rafRef.current);
    };
  }, [scrollRef, blockIds]);

  return activeId;
}
