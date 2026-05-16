"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const SUBJECTS_MOBILE_BG = "/img/bg-subjects-sm.jpg";

const SUBJECT_OPTIONS = [
  { name: "Русский язык", board: "ЕГЭ", icon: "/img/subj-economics.svg", img: "/img/subjects-economics.avif" },
  { name: "Математика", board: "ЕГЭ", icon: "/img/subj-physics.svg", img: "/img/subjects-physics.avif" },
  { name: "Информатика", board: "ЕГЭ", icon: "/img/subj-business.svg", img: "/img/subjects-business.avif" },
  { name: "Биология", board: "ЕГЭ", icon: "/img/subj-biology.svg", img: "/img/subjects-biology.avif" },
  { name: "Химия", board: "ЕГЭ", icon: "/img/subj-chemistry.svg", img: "/img/subjects-chemistry.avif" },
  { name: "Физика", board: "ЕГЭ", icon: "/img/subj-psychology.svg", img: "/img/subjects-psychology.avif" },
] as const;

/** Warm HTTP cache for all subject hero images so tile switches are instant (runs when main thread is idle). */
function preloadSubjectVisuals() {
  for (const s of SUBJECT_OPTIONS) {
    const img = new Image();
    img.decoding = "async";
    img.src = s.img;
  }
  const bg = new Image();
  bg.decoding = "async";
  bg.src = SUBJECTS_MOBILE_BG;
}

export function LandingSubjectsSection() {
  const [activeKey, setActiveKey] = useState<string>(SUBJECT_OPTIONS[0].name);

  useEffect(() => {
    let cancelled = false;
    const run = () => {
      if (cancelled) return;
      preloadSubjectVisuals();
    };

    if (typeof window.requestIdleCallback === "function") {
      const id = window.requestIdleCallback(run, { timeout: 5000 });
      return () => {
        cancelled = true;
        window.cancelIdleCallback(id);
      };
    }

    const t = window.setTimeout(run, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, []);

  return (
    <section id="subjects" className="subjects-section relative">
      <div
        className="pointer-events-none absolute inset-0 rounded-[32px] bg-cover bg-center bg-no-repeat sm:hidden"
        style={{ backgroundImage: `url('${SUBJECTS_MOBILE_BG}')` }}
        aria-hidden
      />

      <div className="subjects-container relative">
        <div className="subjects-grid">
          <div className="subjects-left">
            <p className="subjects-eyebrow max-sm:text-center">Предметы</p>
            <h2 className="subjects-title max-sm:text-center">
              Выбери
              <br className="hidden sm:block" />
              <span className="subjects-title-accent">предмет ЕГЭ</span>
            </h2>
            <p className="subjects-sub max-sm:text-center">
              Уроки, практика, прогресс и ошибки собраны вокруг выбранного предмета.
            </p>

            <div className="subject-tiles">
              {SUBJECT_OPTIONS.map((s) => (
                <button
                  key={s.name}
                  type="button"
                  data-key={s.name}
                  onClick={() => setActiveKey(s.name)}
                  className={`subject-tile${activeKey === s.name ? " is-active" : ""}`}
                >
                  <img className="subject-icon" src={s.icon} alt="" aria-hidden width={24} height={24} loading="lazy" decoding="async" />
                  <span className="subject-name">{s.name}</span>
                  <span className="subject-board">{s.board}</span>
                </button>
              ))}
            </div>

            <div className="subjects-cta-row">
              <Link href="/registration" className="subjects-cta">
                Открыть первый урок
              </Link>
            </div>
          </div>

          <div className="subjects-visual max-sm:hidden">
            {SUBJECT_OPTIONS.map((s) => (
              <img
                key={s.name}
                src={s.img}
                alt={activeKey === s.name ? `${s.name}: экран подготовки` : ""}
                aria-hidden={activeKey !== s.name}
                data-key={s.name}
                className={`subjects-visual-img${activeKey === s.name ? " is-active" : ""}`}
                loading="eager"
                decoding="async"
                fetchPriority={activeKey === s.name ? "high" : "low"}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
