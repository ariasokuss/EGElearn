const info = [
  { title: "Готовность", content: "Смотри, какие темы уже держатся уверенно, а какие требуют повторения" },
  {
    title: "Прогноз",
    content: "Понимай, какие темы сильнее всего двигают ожидаемый балл",
  },
];

export function LandingRoadmapSection() {
  return (
    <section id="roadmap" className="relative overflow-x-hidden bg-white py-24 max-sm:pt-0">
      <div className="mx-auto max-w-6xl px-6 text-center">
        <p
          style={{
            color: "#91847C",
            textAlign: "center",
            fontFamily: "KaTeX_Main",
            fontSize: "22px",
          }}
        >
          Прогресс
        </p>
        <h2 className="roadmap-title">
          Видишь слабые темы <span className="roadmap-title-accent">до того,</span>
          <br className="hidden sm:block" />
          <span className="roadmap-title-accent">как они заберут баллы</span>
        </h2>
        <p
          style={{
            color: "#2A201A",
            textAlign: "center",
            fontFamily: "Inter",
            fontSize: "17px",
            lineHeight: "28px",
            maxWidth: "36rem",
            marginInline: "auto",
            marginTop: "26px",
          }}
        >
          Готовность, прогноз, серия занятий и ошибки обновляются после уроков и практики.
        </p>

        <div className="relative mt-16">
          <div className="hero-media ege-dashboard mx-auto max-w-5xl">
            <div className="ege-dashboard-top">
              <div>
                <p className="ege-dashboard-kicker">Сегодня</p>
                <h2>Темы, которые двигают балл</h2>
              </div>
              <div className="ege-dashboard-ai">YandexGPT объяснит второй способ</div>
            </div>
            <div className="ege-dashboard-stats">
              {["Готовность", "Прогноз", "Серия", "Ошибки"].map((label, index) => (
                <button key={label} type="button" className={index === 0 ? "is-active" : ""}>
                  <span>{label}</span>
                  <strong>{["72%", "+11", "8", "14"][index]}</strong>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="relative -mt-[95px] hidden max-sm:flex max-sm:flex-col max-sm:items-center max-sm:gap-3">
          {info.map((i) => (
            <div
              key={i.title}
              className="flex max-w-80 flex-col gap-2.5 rounded-[16px] border border-[#ECECED] bg-white px-5 py-4 text-start"
            >
              <p style={{ fontFamily: "KaTeX_Main", fontSize: "24px", color: "#1A1714" }}>{i.title}</p>
              <p style={{ fontSize: "14.5px", color: "#3F3F46" }}>{i.content}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
