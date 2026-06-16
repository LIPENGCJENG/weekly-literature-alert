import logging
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

LOGGER = logging.getLogger(__name__)


def build_email_message(
    html_body: str,
    config: dict[str, Any],
    report_date: date | None = None,
    markdown_body: str | None = None,
) -> MIMEMultipart:
    report_date = report_date or date.today()
    email_config = config.get("email", {})
    profile = config.get("profile", {})
    sender = os.getenv("SMTP_USER", profile.get("email_from", ""))
    recipient = os.getenv("EMAIL_TO", profile.get("email_to", ""))
    subject = f"{email_config.get('subject_prefix', '[每周文献推送]')} 复合固态电解质与锂离子传导机理 - {report_date.isoformat()}"

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    if markdown_body:
        message.attach(MIMEText(markdown_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))
    return message


def send_email(html_body: str, config: dict[str, Any], report_date: date | None = None, markdown_body: str | None = None) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", config.get("email", {}).get("smtp_port", 587)))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    recipient = os.getenv("EMAIL_TO", config.get("profile", {}).get("email_to", ""))
    use_tls = bool(config.get("email", {}).get("use_tls", True))

    if not all([smtp_host, smtp_user, smtp_password, recipient]) or "example.com" in recipient:
        LOGGER.warning("Email credentials or recipient are incomplete; report was generated but not sent.")
        return False

    message = build_email_message(html_body, config, report_date=report_date, markdown_body=markdown_body)
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            if use_tls:
                server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [recipient], message.as_string())
        LOGGER.info("Report email sent to %s", recipient)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        LOGGER.error("Failed to send report email: %s", exc)
        return False
