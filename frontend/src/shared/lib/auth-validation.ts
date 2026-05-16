const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD_LENGTH = 8;
const PASSWORD_HAS_LETTER = /[a-zA-Z]/;
const PASSWORD_HAS_NUMBER = /\d/;
const CODE_REGEX = /^\d{6}$/;

export type AuthValidationErrors = {
  email?: string;
  password?: string;
  passwordConfirm?: string;
  code?: string;
};

export function validateEmail(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return "Email is required";
  if (!EMAIL_REGEX.test(trimmed)) return "Enter a valid email address";
  return undefined;
}

export function validateEmailForLogin(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return "Email is required";
  if (!trimmed.includes("@")) return "Enter a valid email address";
  return undefined;
}

export function validatePassword(value: string, fieldName = "Password"): string | undefined {
  if (!value) return `${fieldName} is required`;
  if (value.length < MIN_PASSWORD_LENGTH)
    return `${fieldName} must be at least ${MIN_PASSWORD_LENGTH} characters`;
  if (!PASSWORD_HAS_LETTER.test(value))
    return `${fieldName} must contain at least one letter`;
  if (!PASSWORD_HAS_NUMBER.test(value))
    return `${fieldName} must contain at least one number`;
  return undefined;
}

export function validatePasswordMatch(
  password: string,
  passwordConfirm: string
): string | undefined {
  if (!passwordConfirm) return "Please repeat the password";
  if (password !== passwordConfirm) return "Passwords do not match";
  return undefined;
}

export function validateCode(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return "Enter the code";
  if (!CODE_REGEX.test(trimmed)) return "Code must be 6 digits";
  return undefined;
}
