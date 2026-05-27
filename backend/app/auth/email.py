"""EmailService — Mailpit (dev) ↔ Resend (staging/prod) switch (D-05, D-06, D-07).

Researcher correction to CONTEXT D-06: there is no formal ``BaseEmailSender``
protocol in fastapi-users; this class is plain Python injected into
``UserManager.__init__``. The UserManager hooks call
``self.email_service.send_verification_email(...)`` / ``send_reset_password_email(...)``.

Mailpit branch uses ``aiosmtplib`` against ``settings.SMTP_HOST:settings.SMTP_PORT``
(no auth, no TLS — dev convenience). Resend branch uses ``resend.Emails.send_async``
(verified in RESEARCH §"Pattern 3" lines 614-684 + answer A4 line 1393).

HTML templates are inline f-strings per D-07 — Phase 10 adds Jinja2/branding.

Pitfall 5 (RESEARCH lines 1000-1014) is mitigated at the caller layer
(UserManager.on_after_register wraps email send in try/except); EmailService
itself does NOT swallow exceptions — the caller decides.
"""

from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib
import resend

from app.core.config import get_settings

# splitting markup would obscure the rendered result.
VERIFY_HTML = (
    "<!doctype html>"
    "<html><body style=\"font-family:system-ui,sans-serif\">"
    "<h2>Verify your XPredict account</h2>"
    "<p>Click the link below to verify your email address. "
    "The link is single-use and expires in 1 hour.</p>"
    "<p><a href=\"{verify_url}\" "
    "style=\"background:#000;color:#fff;padding:10px 16px;text-decoration:none\">"
    "Verify email</a></p>"
    "<p style=\"color:#666;font-size:12px\">"
    "If the button does not work, paste this URL into your browser: "
    "{verify_url}</p>"
    "</body></html>"
)

RESET_HTML = (
    "<!doctype html>"
    "<html><body style=\"font-family:system-ui,sans-serif\">"
    "<h2>Reset your XPredict password</h2>"
    "<p>Click the link below to choose a new password. "
    "The link is single-use and expires in 1 hour.</p>"
    "<p><a href=\"{reset_url}\" "
    "style=\"background:#000;color:#fff;padding:10px 16px;text-decoration:none\">"
    "Reset password</a></p>"
    "<p style=\"color:#666;font-size:12px\">"
    "If you did not request this, you can safely ignore the email. "
    "URL: {reset_url}</p>"
    "</body></html>"
)


class EmailService:
    """One sender to rule them all — env-switched (D-05, D-06)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.is_dev and self.settings.RESEND_API_KEY:
            resend.api_key = self.settings.RESEND_API_KEY

    async def send(self, *, to: str, subject: str, html: str) -> None:
        """Dispatch via Mailpit (dev) or Resend (staging/prod)."""
        if self.settings.is_dev:
            await self._send_via_mailpit(to=to, subject=subject, html=html)
        elif self.settings.RESEND_API_KEY:
            await self._send_via_resend(to=to, subject=subject, html=html)
        else:
            raise RuntimeError(
                "RESEND_API_KEY is required in non-dev environments but was not set."
            )

    async def _send_via_mailpit(self, *, to: str, subject: str, html: str) -> None:
        msg = EmailMessage()
        msg["From"] = f"XPredict <{self.settings.RESEND_FROM_ADDRESS}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content("HTML email — view in a modern client.")
        msg.add_alternative(html, subtype="html")
        await aiosmtplib.send(
            msg,
            hostname=self.settings.SMTP_HOST,
            port=self.settings.SMTP_PORT,
            use_tls=False,
            start_tls=False,
        )

    async def _send_via_resend(self, *, to: str, subject: str, html: str) -> None:
        params: resend.Emails.SendParams = {
            "from": self.settings.RESEND_FROM_ADDRESS,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        await resend.Emails.send_async(params)

    async def send_verification_email(self, *, to: str, token: str) -> None:
        """Send the single-use email-verification link (AUTH-02)."""
        verify_url = f"{self.settings.FRONTEND_BASE_URL}/verify-email?token={token}"
        await self.send(
            to=to,
            subject="Verify your XPredict email",
            html=VERIFY_HTML.format(verify_url=verify_url),
        )

    async def send_reset_password_email(self, *, to: str, token: str) -> None:
        """Send the single-use password-reset link (AUTH-06)."""
        reset_url = f"{self.settings.FRONTEND_BASE_URL}/reset-password?token={token}"
        await self.send(
            to=to,
            subject="Reset your XPredict password",
            html=RESET_HTML.format(reset_url=reset_url),
        )
