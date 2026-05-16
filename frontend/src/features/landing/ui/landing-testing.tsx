const cards = [
  {
    title: "Практика по темам",
    body:
      "Тренируй задания по выбранным темам и сразу возвращайся к ошибкам, которые мешают баллу.",
    icon: "/img/testing-doc.svg",
  },
  {
    title: "Разбор с YandexGPT",
    body:
      "Получай второй способ решения, короткое объяснение и следующий шаг для закрепления.",
    icon: "/img/testing-ai.svg",
  },
];

export function LandingTestingSection() {
  return (
    <section id="testing" className="testing-section">
      <div className="testing-container">
        <p className="testing-eyebrow">Практика</p>
        <h2 className="testing-title">
          Тренируй то,
          <br />
          что двигает балл
        </h2>
        <p className="testing-sub">
          NovaLearn связывает уроки, задания, прогресс и ошибки, чтобы каждый подход к практике был понятным.
        </p>

        <div className="testing-grid">
          {cards.map((c) => (
            <div key={c.title} className="testing-card">
              <img className="testing-icon" src={c.icon} alt="" aria-hidden width={56} height={56} loading="lazy" decoding="async" />
              <h3 className="testing-card-title">{c.title}</h3>
              <p className="testing-card-body">{c.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
