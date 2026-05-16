from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field


class SendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    redirect_url: AnyHttpUrl | None = Field(
        default=None,
        description="Frontend URL to redirect the user to after clicking the reset link. "
        "The raw token will be appended as ?token=<token>.",
    )


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=64, max_length=64)
    new_password: str = Field(min_length=8, max_length=128)


class SendDesktopLinkRequest(BaseModel):
    desktop_url: AnyHttpUrl = Field(
        description="Frontend origin URL the user should open on their desktop "
        "(e.g. https://novalearn.ai). Used as the email CTA href."
    )


class MessageResponse(BaseModel):
    message: str
