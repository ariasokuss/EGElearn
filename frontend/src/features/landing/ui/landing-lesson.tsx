const features = [
  {
    title: "Понятные уроки",
    body:
      "Короткие объяснения, примеры и встроенные вопросы помогают сразу проверить понимание.",
    icon: "/img/lesson-brain.svg",
  },
  {
    title: "Объяснение своими словами",
    body:
      "После темы перескажи решение, а YandexGPT подсветит пропущенные ключевые шаги.",
    icon: "/img/lesson-mic.svg",
  },
  {
    title: "Практика ЕГЭ",
    body:
      "Тренируй задания по типам и темам, чтобы видеть, где теряются баллы.",
    icon: "/img/lesson-pencil.svg",
  },
  {
    title: "Разбор ошибок",
    body:
      "Каждая ошибка превращается в точку повторения: разбери причину и закрепи похожим заданием.",
    icon: "/img/lesson-feedback.svg",
  },
];

export function LandingLessonSection() {
  return (
    <section id="lesson" className="lesson-section">
      <div className="lesson-container">
        <p className="lesson-eyebrow">Внутри урока</p>
        <h2 className="lesson-title">
          Тема, практика
          <br /> и ошибка рядом
        </h2>
        <p className="lesson-sub">
          Один рабочий экран помогает пройти тему, потренироваться и вернуться к сложным местам.
        </p>

        <div className="lesson-grid">
          {features.map((f) => (
            <div key={f.title} className="lesson-card">
              <img className="lesson-icon" src={f.icon} alt="" aria-hidden width={56} height={56} loading="lazy" decoding="async" />
              <h3 className="lesson-card-title">{f.title}</h3>
              <p className="lesson-card-body">{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
