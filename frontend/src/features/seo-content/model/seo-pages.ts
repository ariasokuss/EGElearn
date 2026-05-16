type BreadcrumbItem = {
  label: string;
  href: string;
};

type RelatedLink = {
  label: string;
  href: string;
};

type ContentSection = {
  heading: string;
  body: string;
};

type FaqItem = {
  question: string;
  answer: string;
};

export type SeoPageDefinition = {
  id: string;
  path: string;
  metadataTitle: string;
  metadataDescription: string;
  pageTitle: string;
  intro: string;
  type?: "website" | "article";
  priority?: number;
  breadcrumbs: BreadcrumbItem[];
  sections: ContentSection[];
  relatedLinks: RelatedLink[];
  faq?: FaqItem[];
};

export const seoPages: SeoPageDefinition[] = [
  {
    id: "ege",
    path: "/ege",
    metadataTitle: "Предметы ЕГЭ",
    metadataDescription: "Предметы ЕГЭ в NovaLearn: уроки, практика, прогресс и разбор ошибок.",
    pageTitle: "Предметы ЕГЭ",
    intro: "Выбери предмет ЕГЭ и работай с уроками, практикой, прогрессом и ошибками в одном месте.",
    breadcrumbs: [{ label: "ЕГЭ", href: "/ege" }],
    sections: [
      {
        heading: "Подготовка по предметам",
        body: "Выбирай предмет, проходи темы, тренируй задания и возвращайся к ошибкам.",
      },
    ],
    relatedLinks: [],
    faq: [
      {
        question: "Есть ли готовые дорожные карты по ФИПИ?",
        answer:
          "Структура платформы готова, а дорожные карты будут наполняться на основе материалов ФИПИ в отдельном контентном этапе.",
      },
    ],
  },
];

export function getSeoPage(id: SeoPageDefinition["id"]) {
  const page = seoPages.find((item) => item.id === id);

  if (!page) {
    throw new Error(`SEO page definition not found: ${id}`);
  }

  return page;
}

export function getSeoPaths() {
  return seoPages.map((page) => page.path);
}
