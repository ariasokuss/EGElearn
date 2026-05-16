"use client";

import { useHowItWorksEffects } from "../use-how-it-works";

const steps = [
  {
    title: "Выбери предмет",
    body: "Открой русский язык, математику, информатику или другой предмет ЕГЭ и начни с понятной карты тем.",
  },
  {
    title: "Проходи уроки",
    body: "Разбирай тему короткими блоками, закрепляй заданиями и смотри, как меняется готовность.",
  },
  {
    title: "Тренируй практику",
    body: "Решай задания по темам и отслеживай прогноз, серию занятий и слабые места.",
  },
  {
    title: "Разбирай ошибки",
    body: "Возвращайся к ошибкам и проси YandexGPT показать второй способ, когда решение не складывается.",
  },
] as const;

function HowItWorksLoader({ id }: { id: number }) {
  return (
    <div id={`howit-loader-${id}`} className="howit-loader">
      <div className="howit-loader-content">
        <img src="/img/howit-check.svg" alt="" className="howit-loader-check" />
        <img src="/img/howit-book.svg" alt="" />
      </div>
    </div>
  );
}

export function LandingHowItWorks() {
  useHowItWorksEffects();

  return (
    <section id="how-it-works" className="howit-section relative bg-white py-24 max-sm:pt-0">
      <div className="howit-gridbg" aria-hidden />

      <svg
        className="howit-curve"
        aria-hidden="true"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="none"
      >
        <defs>
          <mask id="howit-curve-path-mask">
            <path
              id="howit-curve-path-mask-path"
              d=""
              fill="none"
              stroke="white"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="5"
            />
          </mask>
          <linearGradient id="howit-curve-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0.04" stopColor="#E2DCDA" stopOpacity="0.19" />
            <stop offset="0.3" stopColor="#7C7978" stopOpacity="0.51" />
          </linearGradient>
        </defs>
        <path
          id="howit-curve-path"
          d=""
          fill="none"
          stroke="url(#howit-curve-grad)"
          strokeWidth="4.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="0.5 16"
          mask="url(#howit-curve-path-mask)"
          opacity="0.6"
        />
      </svg>

      <svg
        className="howit-curve howit-curve-exit"
        aria-hidden="true"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="none"
      >
        <defs>
          <mask id="howit-curve-exit-mask">
            <path
              id="howit-curve-exit-mask-path"
              d=""
              fill="none"
              stroke="white"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="5"
            />
          </mask>
          <linearGradient id="howit-curve-exit-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0.04" stopColor="#E2DCDA" stopOpacity="0.79" />
            <stop offset="0.4" stopColor="#7C7978" stopOpacity="0.6" />
          </linearGradient>
        </defs>

        <path
          id="howit-curve-exit-path"
          d=""
          fill="none"
          stroke="url(#howit-curve-exit-grad)"
          strokeWidth="4.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="0.5 16"
          mask="url(#howit-curve-exit-mask)"
          opacity="0.6"
        />
      </svg>

      <div className="relative mx-auto max-w-6xl px-6">
        <div className="howit-grid">
          <div className="howit-intro">
            <p id="howit-label" className="howit-eyebrow">
              Как это работает
            </p>
            <h2 id="howit-title" className="howit-title">
              Четыре шага
              <br className="hidden sm:block" /> к готовности
              <br className="hidden sm:block" /> к ЕГЭ
            </h2>
            <p className="howit-sub">
              NovaLearn держит предметы, уроки, практику, прогресс и ошибки в одном рабочем ритме.
            </p>
          </div>

          <ol className="timeline">
            {steps.map((step, i) => (
              <li key={step.title} className="timeline-item">
                <HowItWorksLoader id={i} />
                <div className="timeline-text">
                  <h3 className="timeline-title">{step.title}</h3>
                  <p className="timeline-body">{step.body}</p>
                </div>
                {i < steps.length - 1 ? (
                  <div className="timeline-line" aria-hidden="true">
                    <div id={`timeline-line-${i}`} className="timeline-line-fill" />
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
