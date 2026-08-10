"""验证码邮件发送（PRD 阶段1 邮箱验证）。

- SMTP 未配置（dev 默认）→ 降级仅日志，注册流程不阻断
- 配置后走 smtplib.SMTP_SSL 真实发送
- FakeEmailSender 供测试断言
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailSenderError(Exception):
    pass


def _build_message(to_email: str, code: str, smtp_from: str) -> str:
    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg["Subject"] = "谋谈 MouTalk 邮箱验证码"
    text = (
        f"您好！\n\n"
        f"您的谋谈 MouTalk 注册验证码为：{code}\n"
        f"验证码 10 分钟内有效，请勿泄露给他人。\n\n"
        f"—— 谋谈 MouTalk 团队"
    )
    msg.attach(MIMEText(text, "plain", "utf-8"))
    return msg.as_string()


def send_verification_email(to_email: str, code: str) -> None:
    """发送验证码邮件。SMTP 未配置时降级仅日志（dev 默认行为）。"""
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from:
        logger.info("SMTP 未配置，验证码邮件降级为日志输出: %s -> %s", to_email, code)
        return
    body = _build_message(to_email, code, settings.smtp_from)
    try:
        server = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=10
        )
        try:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from, [to_email], body)
        finally:
            server.quit()
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("验证码邮件发送失败: %s -> %s (%s)", to_email, code, exc)
        raise EmailSenderError("邮件发送失败") from exc
    logger.info("验证码邮件已发送: %s", to_email)


class FakeEmailSender:
    """测试用发件器：记录 (email, code) 调用。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def __call__(self, email: str, code: str) -> None:
        self.sent.append((email, code))
