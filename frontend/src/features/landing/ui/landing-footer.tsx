"use client";

import Link from "next/link";

const navItems = [
  { label: "Как это работает", href: "#how-it-works" },
  { label: "Прогресс", href: "#roadmap" },
  { label: "Уроки", href: "#lesson" },
  { label: "Предметы", href: "#subjects" },
  { label: "Практика", href: "#testing" },
  { label: "Старт", href: "#results" },
];

export function LandingFooterSection() {
  return (
    <footer className="site-footer">
      <div className="footer-band">
        <div className="footer-band-inner">
          <Link href="/" className="footer-brand" aria-label="NovaLearn">
            <img src="/img/logo-full.svg" alt="NovaLearn" className="footer-logo" width={113} height={31} />
          </Link>
          <nav className="footer-nav">
            <ul>
              {navItems.map((item) => (
                <li key={item.href}>
                  <a href={item.href} className="footer-nav-link">
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </div>

      <div className="footer-dark">
        <div className="footer-dark-inner">
          <div className="footer-legal-links">
            <a href="#terms">Условия</a>
            <a href="#privacy">Конфиденциальность</a>
          </div>
          <div className="footer-copyright">© 2026 NovaLearn</div>
        </div>
      </div>
    </footer>
  );
}
