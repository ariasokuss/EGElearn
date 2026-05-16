"use client";

import { LandingFinalCtaSection } from "./landing-final-cta";
import { LandingFooterSection } from "./landing-footer";
import { LandingHeader } from "./landing-header";
import { LandingHero } from "./landing-hero";
import { LandingHowItWorks } from "./landing-how-it-works";
import { LandingLessonSection } from "./landing-lesson";
import { LandingProblemSection } from "./landing-problem";
import { LandingRoadmapSection } from "./landing-roadmap";
import { LandingSubjectsSection } from "./landing-subjects";
import { LandingTestingSection } from "./landing-testing";

export function LandingPage() {
  return (
    <div id="nl-landing-root" className="min-h-screen bg-[var(--nl-cream)]">
      <LandingHeader />
      <main className="min-h-screen bg-[var(--nl-cream)]">
        <LandingHero />
        <LandingProblemSection />
        <LandingHowItWorks />
        <LandingRoadmapSection />
        <LandingLessonSection />
        <LandingSubjectsSection />
        <LandingTestingSection />
        <LandingFinalCtaSection />
      </main>
      <LandingFooterSection />
    </div>
  );
}
