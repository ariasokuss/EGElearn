"use client";

import Link from "next/link";

const cards = [
  {
    title: "Темы без системы",
    body:
      "Сложно понять, с чего начать и какие темы сильнее всего влияют на балл.",
    img: "/img/problem-cap.svg",
  },
  {
    title: "Конспекты\nне проверяют",
    body:
      "Можно читать долго, но не заметить, что решение не получается без подсказки.",
    img: "/img/problem-book.svg",
  },
  {
    title: "Ошибки теряются",
    body:
      "Если не возвращаться к ошибкам, они снова появляются в похожих заданиях.",
    img: "/img/problem-atom.svg",
  },
];

export function LandingProblemSection() {
  return (
    <section id="outcomes" className="problem-section">
      <span className="dotted-line dotted-line-top" aria-hidden />
      <div className="mx-auto max-w-6xl px-6 text-center">
        <div className="spark-wrap">
          <img src="/img/star.svg" alt="" aria-hidden className="spark" />
        </div>
        <span className="dotted-line dotted-line-after-star" aria-hidden />

        <p className="eyebrow">Задача</p>
        <h2 className="problem-title mx-auto mt-4 max-w-[1100px]">
          ЕГЭ требует регулярной практики.
          <br className="hidden sm:block" /> Важно видеть, что именно повторять.
        </h2>
        <p className="problem-sub mx-auto mt-5 max-w-xl">
          NovaLearn связывает предметы, уроки, задания и ошибки, чтобы подготовка не распадалась на отдельные вкладки.
        </p>

        <div className="mt-8 flex justify-center">
          <Link href="/registration" className="cta-muted">
            Начать подготовку
          </Link>
        </div>

        <div className="cards-grid">
          {cards.map((card) => (
            <div key={card.img} className="problem-card">
              <img src={card.img} alt="" aria-hidden className="illus" loading="lazy" decoding="async" />
              <div className="card-text">
                <h3 className="card-title">{card.title}</h3>
                <div className="card-divider" />
                <p className="card-body">{card.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
