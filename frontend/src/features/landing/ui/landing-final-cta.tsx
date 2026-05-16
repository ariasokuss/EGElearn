"use client";

import Link from "next/link";

export function LandingFinalCtaSection() {
  return (
    <section id="results" className="final-cta-section">
      <div className="final-cta-container">
        <h2 className="final-cta-title">Готовиться к ЕГЭ проще по плану</h2>
        <p className="final-cta-sub">Выбери предмет и начни с уроков, практики и разбора ошибок.</p>
        <div className="final-cta-row">
          <Link href="/registration" className="final-cta-btn">
            Начать подготовку
          </Link>
        </div>
        <p className="final-cta-note">NovaLearn помогает держать предметы ЕГЭ в одном рабочем экране</p>
        <div className="final-cta-divider max-sm:hidden" aria-hidden />
      </div>
    </section>
  );
}
