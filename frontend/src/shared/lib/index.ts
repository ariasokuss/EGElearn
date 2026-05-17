import { twMerge } from "tailwind-merge";

export function cn(...classes: (string | undefined | false)[]): string {
  return twMerge(classes.filter(Boolean).join(" "));
}

export {
  validateEmail,
  validateEmailForLogin,
  validatePassword,
  validatePasswordMatch,
  validateCode,
  type AuthValidationErrors,
} from "./auth-validation";

export {
  getAccessToken,
  getRefreshToken,
  setTokens,
  clearTokens,
} from "./auth-storage";

export { formatApiValidationError } from "./api-error";

export {
  getPublicAppOrigin,
  getPasswordResetRedirectUrl,
  getPasswordResetUrlTemplateForBackend,
  PASSWORD_RESET_TOKEN_PARAM,
} from "./public-app-url";

export { useAutoHideScrollbar } from "./use-auto-hide-scrollbar";

export { TestGuardProvider, useTestGuard } from "./test-guard-context";

export {
  getPublicBaseUrl,
  toAbsoluteUrl,
  buildRobotsPolicy,
  buildPageMetadata,
  buildOrganizationSchema,
  buildWebsiteSchema,
  buildBreadcrumbSchema,
  buildFaqSchema,
} from "./seo";

export { trackSeoEvent } from "./seo-analytics";

export { detectIsPhoneUserAgent } from "./device/detect-is-phone";
