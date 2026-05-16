"""Async Resend HTTPS API mail client."""

from __future__ import annotations

import logging

import httpx

from src.config import MailSettings

logger = logging.getLogger(__name__)


class MailError(Exception):
    """Raised when sending an email via Resend fails."""


class MailClient:
    """
    Thin async client for the Resend HTTPS API.

    Stateless — each `send()` opens an httpx connection. Resend uses simple
    bearer-token auth and a single POST /emails endpoint.
    """

    def __init__(self, settings: MailSettings) -> None:
        self._settings = settings

    async def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        reply_to: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> None:
        """Send an HTML email to a single recipient via Resend."""
        if not self._settings.api_key:
            raise MailError("Resend API key is not configured (MAIL__API_KEY).")

        effective_from_email = from_email or self._settings.from_email
        effective_from_name = from_name or self._settings.from_name
        effective_reply_to = reply_to or self._settings.reply_to or effective_from_email

        payload: dict[str, object] = {
            "from": f"{effective_from_name} <{effective_from_email}>",
            "to": [to],
            "subject": subject,
            "html": html_body,
            "reply_to": effective_reply_to,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._settings.timeout) as client:
                response = await client.post(
                    f"{self._settings.api_url.rstrip('/')}/emails",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            logger.error("Resend network error sending to=%s: %s", to, exc)
            raise MailError(f"Failed to send email: {exc}") from exc

        if response.status_code >= 400:
            logger.error(
                "Resend API error sending to=%s status=%s body=%s",
                to,
                response.status_code,
                response.text,
            )
            raise MailError(
                f"Resend API returned {response.status_code}: {response.text}"
            )

        message_id = ""
        try:
            message_id = response.json().get("id", "")
        except ValueError:
            pass

        logger.info("Email sent to=%s subject=%r id=%s", to, subject, message_id)

    async def send_security(
        self,
        to: str,
        subject: str,
        html_body: str,
    ) -> None:
        """Send a security email (verification, password reset, account changes) from the dedicated security identity."""
        await self.send(
            to=to,
            subject=subject,
            html_body=html_body,
            from_email=self._settings.security_from_email or self._settings.from_email,
            from_name=self._settings.security_from_name or self._settings.from_name,
            reply_to=self._settings.security_from_email or self._settings.from_email,
        )
