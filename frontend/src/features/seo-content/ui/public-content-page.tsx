import Link from "next/link";
import { buildBreadcrumbSchema, buildFaqSchema } from "@/shared/lib";
import { SeoCtaLink } from "./seo-cta-link";

type ContentSection = {
  heading: string;
  body: string;
};

type FaqItem = {
  question: string;
  answer: string;
};

type PublicContentPageProps = {
  title: string;
  intro: string;
  breadcrumbs: Array<{ label: string; href: string }>;
  sections: ContentSection[];
  relatedLinks: Array<{ label: string; href: string }>;
  faq?: FaqItem[];
};

export function PublicContentPage({
  title,
  intro,
  breadcrumbs,
  sections,
  relatedLinks,
  faq = [],
}: PublicContentPageProps) {
  const breadcrumbSchema = buildBreadcrumbSchema(
    breadcrumbs.map((item) => ({ name: item.label, path: item.href })),
  );
  const faqSchema = faq.length
    ? buildFaqSchema(faq.map((item) => ({ question: item.question, answer: item.answer })))
    : null;

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-10">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbSchema) }}
      />
      {faqSchema ? (
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} />
      ) : null}

      <nav aria-label="Breadcrumbs" className="flex flex-wrap items-center gap-2 text-sm text-[#71717A]">
        {breadcrumbs.map((item, index) => (
          <span key={item.href} className="flex items-center gap-2">
            {index > 0 ? <span>/</span> : null}
            <Link href={item.href} className="hover:underline">
              {item.label}
            </Link>
          </span>
        ))}
      </nav>

      <header className="flex flex-col gap-4">
        <h1 className="font-inter text-3xl font-semibold leading-tight text-[#242529]">{title}</h1>
        <p className="max-w-3xl text-base leading-7 text-[#4B5563]">{intro}</p>
        <SeoCtaLink
          href="/registration"
          text="Начать подготовку в NovaLearn"
          eventName="seo_cta_click"
          eventLocation="hero"
        />
      </header>

      <section className="grid gap-4">
        {sections.map((section) => (
          <article key={section.heading} className="rounded-2xl border border-[#E4E4E7] bg-white p-5">
            <h2 className="mb-2 font-inter text-xl font-semibold text-[#242529]">{section.heading}</h2>
            <p className="text-[15px] leading-7 text-[#4B5563]">{section.body}</p>
          </article>
        ))}
      </section>

      {relatedLinks.length ? (
        <section className="rounded-2xl border border-[#E4E4E7] bg-[#FAFAFA] p-5">
          <h2 className="mb-3 font-inter text-xl font-semibold text-[#242529]">Связанные страницы</h2>
          <ul className="grid gap-2">
            {relatedLinks.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className="text-[#1D4ED8] hover:underline">
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {faq.length ? (
        <section className="rounded-2xl border border-[#E4E4E7] bg-white p-5">
          <h2 className="mb-3 font-inter text-xl font-semibold text-[#242529]">Вопросы</h2>
          <div className="grid gap-4">
            {faq.map((item) => (
              <article key={item.question}>
                <h3 className="font-inter text-base font-semibold text-[#242529]">{item.question}</h3>
                <p className="mt-1 text-[15px] leading-7 text-[#4B5563]">{item.answer}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}
