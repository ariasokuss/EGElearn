"""Jinja2 email template renderer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_verification_email(code: str) -> str:
    """Render the 6-digit verification code email."""
    return _env.get_template("verification_code.html").render(code=code)


def render_email_change_notice(new_email: str) -> str:
    """Render the security notice sent to the *old* email when an email change is requested."""
    return _env.get_template("email_change_notice.html").render(new_email=new_email)


def render_email_change_code(code: str, new_email: str) -> str:
    """Render the verification code email sent to the *new* address during an email change."""
    return _env.get_template("email_change_code.html").render(
        code=code, new_email=new_email
    )


def render_password_reset_email(
    token: str,
    expires_at: datetime | None = None,
    reset_link: str | None = None,
) -> str:
    """Render the password reset token email."""
    expires_str = expires_at.strftime("%-d %B %Y at %H:%M UTC") if expires_at else None
    return _env.get_template("password_reset.html").render(
        token=token,
        reset_link=reset_link,
        expires_str=expires_str,
    )


def render_desktop_link_email(
    desktop_url: str,
    display_url: str,
) -> str:
    """Render the 'open NovaLearn on your computer' email."""
    return _env.get_template("desktop_link.html").render(
        desktop_url=desktop_url,
        display_url=display_url,
    )
