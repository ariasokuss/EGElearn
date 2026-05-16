import { AUTH_ILLUSTRATION_SRC } from "./auth-decor-shell";

export function AuthIllustrationPreload() {
  return (
    <link
      rel="preload"
      as="image"
      href={AUTH_ILLUSTRATION_SRC}
      fetchPriority="high"
      media="(min-width: 1024px)"
    />
  );
}
