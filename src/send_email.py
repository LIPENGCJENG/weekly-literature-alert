import logging
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

LOGGER = logging.getLogger(__name__)


def _is_english(config: dict[str, Any]) -> bool:
    language = str(config.get("email", {}).get("language", "Chinese")).strip().lower()
    return language in {"english", "en", "英语"}


def _email_subject(config: dict[str, Any], report_date: date) -> str:
    email_config = config.get("email", {})
    english = _is_english(config)
    configured_prefix = str(email_config.get("subject_prefix", "")).strip()
    if english and configured_prefix in {"", "[每周文献推送]"}:
        prefix = "[Weekly Literature Alert]"
    else:
        prefix = configured_prefix or "[每周文献推送]"
    default_topic = "Latest Literature Update" if english else "复合固态电解质与锂离子传导机理"
    topic = str(email_config.get("subject_topic", default_topic)).strip() or default_topic
    return f"{prefix} {topic} - {report_date.isoformat()}"


def build_email_message(
    html_body: str,
    config: dict[str, Any],
    report_date: date | None = None,
    markdown_body: str | None = None,
) -> MIMEMultipart:
    report_date = report_date or date.today()
    profile = config.get("profile", {})
    sender = os.getenv("SMTP_USER", profile.get("email_from", ""))
    recipient = os.getenv("EMAIL_TO", profile.get("email_to", ""))
    subject = _email_subject(config, report_date)

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
