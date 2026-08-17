"""Gmail SMTP 발송."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

log = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"


def _send_starttls(msg, user, app_password, recipients, port=587) -> None:
    with smtplib.SMTP(SMTP_HOST, port, timeout=30) as server:
        server.starttls()
        server.login(user, app_password)
        server.sendmail(user, recipients, msg.as_string())


def _send_ssl(msg, user, app_password, recipients, port=465) -> None:
    with smtplib.SMTP_SSL(SMTP_HOST, port, timeout=30) as server:
        server.login(user, app_password)
        server.sendmail(user, recipients, msg.as_string())


def send_email(
    *,
    user: str,
    app_password: str,
    recipients: list[str],
    subject: str,
    html: str,
    sender_name: str = "News Brief Bot",
) -> None:
    if not (user and app_password and recipients):
        raise ValueError("EMAIL_USER / EMAIL_APP_PASSWORD / EMAIL_TO 가 필요합니다.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((sender_name, user))
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText("HTML 본문을 지원하는 메일 클라이언트에서 확인하세요.", "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    # 587(STARTTLS) 우선, 막혀 있으면 465(SSL) 폴백
    try:
        _send_starttls(msg, user, app_password, recipients)
    except OSError as e:
        log.warning("587 STARTTLS 실패(%s), 465 SSL 로 재시도", e)
        _send_ssl(msg, user, app_password, recipients)
    log.info("메일 발송 완료 → %s", ", ".join(recipients))
