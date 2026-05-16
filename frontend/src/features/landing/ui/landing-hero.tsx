"use client";

import Link from "next/link";
import { useState } from "react";

const TABS = [
  { key: "ready", label: "Готовность", value: "72%" },
  { key: "forecast", label: "Прогноз", value: "+11" },
  { key: "streak", label: "Серия", value: "8" },
  { key: "mistakes", label: "Ошибки", value: "14" },
] as const;

export function LandingHero() {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]["key"]>("ready");

  return (
    <section className="hero relative overflow-hidden max-sm:h-275 max-sm:rounded-b-[32px]">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(80% 95% at 22% 100%, #ed9474 0%, #f0b38d 24%, rgba(241,188,153,.78) 42%, rgba(248,232,216,0) 68%), radial-gradient(65% 80% at 78% 18%, #fbebda 0%, #f7e4d4 40%, rgba(247,228,215,0) 70%), linear-gradient(180deg, #f3e1d5 0%, #f8e5d7 28%, #f3d6c2 59%, #efb58e 100%)",
        }}
        aria-hidden
      />

      <div className="relative mx-auto max-w-6xl px-6 pb-20 pt-[140px] text-center max-sm:pb-0 md:pt-[160px]">
        <div className="brand-lockup">
          <img src="/img/logo-full.svg" alt="NovaLearn" className="brand-logo mx-auto block h-7 w-auto" />
        </div>
        <h1 className="hero-title mx-auto mt-5 max-w-[1000px]">
          Подготовка к ЕГЭ по предметам
        </h1>
        <p className="hero-sub mx-auto mt-6 max-w-xl">
          Готовность, прогноз, серия занятий и ошибки в одном рабочем экране.
        </p>

        <div className="tabs-row mt-10 flex flex-col-reverse flex-wrap items-center justify-center gap-4 sm:flex-row">
          <span className="tabs-line" aria-hidden />
          <div className="tabs-wrap inline-flex flex-wrap items-center justify-center gap-1 sm:mr-3" role="tablist">
            {TABS.map((t, i) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                data-tab={t.key}
                data-ind={i}
                aria-selected={activeTab === t.key ? "true" : "false"}
                className={`tab-btn relative overflow-hidden ${activeTab === t.key ? "tab-btn-active" : "tab-btn-inactive"}`}
                onClick={() => setActiveTab(t.key)}
              >
                <div className="ease-linear absolute inset-y-px right-full w-full rounded-full border border-[#ededed] bg-transparent transition-[right]" />
                <span>{t.label}</span>
              </button>
            ))}
          </div>
          <Link href="/registration" className="start-btn max-sm:mb-9">
            Начать подготовку
          </Link>
          <span className="tabs-line max-sm:hidden" aria-hidden />
        </div>

        <div className="mt-12">
          <div className="hero-media ege-dashboard mx-auto max-w-5xl">
            <div className="ege-dashboard-top">
              <div>
                <p className="ege-dashboard-kicker">Сегодня</p>
                <h2>Темы, которые двигают балл</h2>
              </div>
              <div className="ege-dashboard-ai">YandexGPT объяснит второй способ</div>
            </div>

            <div className="ege-dashboard-stats">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  className={activeTab === tab.key ? "is-active" : ""}
                  onClick={() => setActiveTab(tab.key)}
                >
                  <span>{tab.label}</span>
                  <strong>{tab.value}</strong>
                </button>
              ))}
            </div>

            <div className="ege-dashboard-main">
              <div className="ege-topic-list">
                {["Пунктуация в сложном предложении", "Производная и графики", "Алгоритмы и таблицы"].map(
                  (topic, index) => (
                    <div key={topic} className="ege-topic-row">
                      <span>{topic}</span>
                      <div aria-hidden>
                        <i style={{ width: `${String(82 - index * 14)}%` }} />
                      </div>
                    </div>
                  ),
                )}
              </div>
              <div className="ege-lesson-card">
                <p>Следующее занятие</p>
                <strong>Русский язык</strong>
                <span>24 минуты практики и разбор 3 ошибок</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
