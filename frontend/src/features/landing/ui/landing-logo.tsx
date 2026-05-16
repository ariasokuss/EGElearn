"use client";

export function LandingLogo({ className = "" }: { className?: string }) {
  return (
    <div className={`logo-pill ${className}`}>
      {/* Background from CSS uses url(/img/logo-bg.png); decorative */}
      <img src="/img/logo.svg" alt="NovaLearn" className="logo-img" />
    </div>
  );
}
