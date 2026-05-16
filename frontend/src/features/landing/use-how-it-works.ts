"use client";

import { useEffect } from "react";

export function useHowItWorksEffects() {
  useEffect(() => {
    function drawHowItWorksCurve() {
      const svg = document.querySelector(".howit-curve") as SVGSVGElement | null;
      const path = document.getElementById("howit-curve-path") as SVGPathElement | null;
      const maskPath = document.getElementById(
        "howit-curve-path-mask-path",
      ) as SVGPathElement | null;
      const label = document.getElementById("howit-label") as HTMLElement | null;
      const cards = document.querySelectorAll<HTMLElement>("#outcomes .problem-card");
      if (!svg || !path || !maskPath || !label || cards.length < 2) return;

      const section = svg.closest(".howit-section") as HTMLElement | null;
      if (!section) return;

      if (window.innerWidth < 900) {
        svg.style.display = "none";
        return;
      }
      svg.style.display = "";

      const sectionRect = section.getBoundingClientRect();
      const cardRect = cards[1].getBoundingClientRect();
      const labelRect = label.getBoundingClientRect();

      const labelStyle = window.getComputedStyle(label);
      const labelFont = parseFloat(labelStyle.fontSize) || 12;
      const labelTextWidth = ((label.textContent || "").length * labelFont) * 0.75;

      const startX = cardRect.left + cardRect.width / 2 - sectionRect.left;
      const startY = cardRect.bottom - sectionRect.top;
      const endX = labelRect.left + labelTextWidth / 2 - sectionRect.left;
      const endY = labelRect.top - sectionRect.top - 18;

      const padX = 60;
      const padY = 60;
      const minX = Math.min(startX, endX) - padX;
      const minY = Math.min(startY, endY) - padY;
      const maxX = Math.max(startX, endX) + padX;
      const maxY = Math.max(startY, endY) + padY;
      const w = maxX - minX;
      const h = maxY - minY;

      svg.style.left = `${String(minX)}px`;
      svg.style.top = `${String(minY)}px`;
      svg.setAttribute("width", String(w));
      svg.setAttribute("height", String(h));
      svg.setAttribute("viewBox", `0 0 ${String(w)} ${String(h)}`);

      const sx = startX - minX;
      const sy = startY - minY;
      const ex = endX - minX;
      const ey = endY - minY;

      const dx = ex - sx;
      const absDx = Math.abs(dx);
      const dy = ey - sy;

      const c1x = sx - absDx * 0.15;
      const c1y = sy + dy * 0.85;

      const c2x = ex + absDx * 0.25;
      const c2y = ey - dy * 0.95;

      const d = `M ${String(sx)} ${String(sy)} C ${String(c1x)} ${String(c1y)}, ${String(c2x)} ${String(c2y)}, ${String(ex)} ${String(ey)}`;
      path.setAttribute("d", d);
      maskPath.setAttribute("d", d);
      const pathLength = path.getTotalLength();
      maskPath.style.setProperty("--path-length", `${String(pathLength)}px`);
    }

    function drawHowItWorksExitCurve() {
      const svg = document.querySelector(".howit-curve-exit") as SVGSVGElement | null;
      const path = document.getElementById("howit-curve-exit-path") as SVGPathElement | null;
      const maskPath = document.getElementById(
        "howit-curve-exit-mask-path",
      ) as SVGPathElement | null;
      const title = document.getElementById("howit-title") as HTMLElement | null;
      const icon = document.getElementById("howit-loader-0");
      if (!svg || !path || !maskPath || !title || !icon) return;

      const section = svg.closest(".howit-section") as HTMLElement | null;
      if (!section) return;

      if (window.innerWidth < 900) {
        svg.style.display = "none";
        return;
      }
      svg.style.display = "";

      const sectionRect = section.getBoundingClientRect();
      const titleRect = title.getBoundingClientRect();
      const iconRect = icon.getBoundingClientRect();

      const startX = titleRect.right - sectionRect.left + 16;
      const startY = titleRect.top - sectionRect.top + 12;
      const endX = iconRect.left + iconRect.width / 2 - sectionRect.left;
      const endY = iconRect.top - sectionRect.top;

      const padX = 60;
      const padY = 60;
      const minX = Math.min(startX, endX) - padX;
      const minY = Math.min(startY, endY) - padY;
      const maxX = Math.max(startX, endX) + padX;
      const maxY = Math.max(startY, endY) + padY;
      const w = maxX - minX;
      const h = maxY - minY;

      svg.style.left = `${String(minX)}px`;
      svg.style.top = `${String(minY)}px`;
      svg.setAttribute("width", String(w));
      svg.setAttribute("height", String(h));
      svg.setAttribute("viewBox", `0 0 ${String(w)} ${String(h)}`);

      const sx = startX - minX;
      const sy = startY - minY;
      const ex = endX - minX;
      const ey = endY - minY;

      const dx = ex - sx;
      const dy = ey - sy;
      const absDx = Math.abs(dx);

      const arcH = Math.max(28, absDx * 0.35);

      const c1x = sx + absDx;
      const c1y = sy - arcH * 0.8;

      const c2x = ex;
      const c2y = ey - arcH * 0.9;

      const pathD = `M ${String(sx)} ${String(sy)} C ${String(c1x)} ${String(c1y)}, ${String(c2x)} ${String(c2y)}, ${String(ex)} ${String(ey)}`;
      path.setAttribute("d", pathD);
      maskPath.setAttribute("d", pathD);

      const pathLength = path.getTotalLength();
      maskPath.style.setProperty("--path-length", `${String(pathLength)}px`);
    }

    function clearPaths() {
      const curvePath = document.getElementById("howit-curve-path") as SVGPathElement | null;
      const pathExit = document.getElementById("howit-curve-exit-path") as SVGPathElement | null;
      if (!curvePath || !pathExit) return;
      curvePath.setAttribute("d", "");
      pathExit.setAttribute("d", "");
    }

    function positionHowItWorksGridBg() {
      const bg = document.querySelector(".howit-gridbg") as HTMLElement | null;
      const section = document.querySelector(".howit-section") as HTMLElement | null;
      const items = document.querySelectorAll<HTMLElement>("#how-it-works .timeline-item");
      if (!bg || !section || items.length < 4) return;

      if (window.innerWidth < 900) {
        bg.style.display = "none";
        return;
      }
      bg.style.display = "";

      const sectionRect = section.getBoundingClientRect();
      const firstRect = items[0].getBoundingClientRect();
      const fourthRect = items[3].getBoundingClientRect();

      const top = firstRect.top - sectionRect.top;
      const bottom = fourthRect.top - sectionRect.top;

      bg.style.top = `${String(top)}px`;
      bg.style.height = `${String(Math.max(0, bottom - top))}px`;
    }

    function runFn() {
      requestAnimationFrame(() => {
        const isMobile = window.matchMedia("(max-width: 640px)").matches;
        if (isMobile) {
          clearPaths();
        } else {
          drawHowItWorksCurve();
          drawHowItWorksExitCurve();
        }
        positionHowItWorksGridBg();
      });
    }

    const onResize = () => {
      runFn();
    };

    window.addEventListener("load", runFn);
    window.addEventListener("resize", onResize);

    let cancelled = false;
    if (document.fonts?.ready) {
      void document.fonts.ready
        .then(() => {
          if (!cancelled) runFn();
        })
        .catch(() => undefined);
    }
    runFn();

    function clamp(val: number) {
      return Math.min(1, Math.max(0, val));
    }

    function onScroll() {
      const sect = document.getElementById("how-it-works");
      if (!sect) return;
      const sectRect = sect.getBoundingClientRect();
      if (sectRect.top - window.innerHeight > 0 || sectRect.bottom < 0) return;

      const path1 = document.getElementById("howit-curve-path-mask-path");
      const path2 = document.getElementById("howit-curve-exit-mask-path");

      const loader1 = document.getElementById("howit-loader-0");
      const loader2 = document.getElementById("howit-loader-1");
      const loader3 = document.getElementById("howit-loader-2");
      const loader4 = document.getElementById("howit-loader-3");

      const line1 = document.getElementById("timeline-line-0");
      const line2 = document.getElementById("timeline-line-1");
      const line3 = document.getElementById("timeline-line-2");
      if (
        !path1 ||
        !path2 ||
        !loader1 ||
        !loader2 ||
        !loader3 ||
        !loader4 ||
        !line1 ||
        !line2 ||
        !line3
      )
        return;

      const offset = 100;
      const middlePos = window.innerHeight / 2;
      const posWithOffset = middlePos + offset;

      const loader1Top = loader1.getBoundingClientRect().top;
      const loader2Top = loader2.getBoundingClientRect().top;
      const loader3Top = loader3.getBoundingClientRect().top;
      const loader4Top = loader4.getBoundingClientRect().top;

      const path1visibility = clamp((posWithOffset - loader1Top + 240) / 120);
      const path2visibility = clamp((posWithOffset - loader1Top + 120) / 120);

      path1.style.setProperty("--path-visibility", String(path1visibility));
      path2.style.setProperty("--path-visibility", String(path2visibility));

      const loader1progress = clamp((posWithOffset - loader1Top) / 150);

      loader1.style.setProperty("--progress", String(loader1progress));
      loader1.classList.toggle("active", loader1progress > 0);
      loader1.classList.toggle("full", loader1progress >= 1);

      const line1progress = clamp(
        (posWithOffset - loader1Top - 150) / Math.max(1, loader2Top - loader1Top - 150),
      );
      line1.style.setProperty("--progress", String(line1progress));

      const loader2progress = clamp((posWithOffset - loader2Top) / 120);

      loader2.style.setProperty("--progress", String(loader2progress));
      loader2.classList.toggle("active", loader2progress > 0);
      loader2.classList.toggle("full", loader2progress >= 1);

      const line2progress = clamp(
        (posWithOffset - loader2Top - 150) / Math.max(1, loader3Top - loader2Top - 150),
      );
      line2.style.setProperty("--progress", String(line2progress));

      const loader3progress = clamp((posWithOffset - loader3Top) / 120);

      loader3.style.setProperty("--progress", String(loader3progress));
      loader3.classList.toggle("active", loader3progress > 0);
      loader3.classList.toggle("full", loader3progress >= 1);

      const line3progress = clamp(
        (posWithOffset - loader3Top - 150) / Math.max(1, loader4Top - loader3Top - 150),
      );
      line3.style.setProperty("--progress", String(line3progress));

      const loader4progress = clamp((posWithOffset - loader4Top) / 120);

      loader4.style.setProperty("--progress", String(loader4progress));
      loader4.classList.toggle("active", loader4progress > 0);
      loader4.classList.toggle("full", loader4progress >= 1);
    }

    window.addEventListener("scroll", onScroll);

    return () => {
      window.removeEventListener("load", runFn);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onScroll);
      cancelled = true;
    };
  }, []);
}
