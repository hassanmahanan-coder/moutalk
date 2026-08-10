"""邮件发送测试：验证码邮件构造、SMTP 未配置降级、发送调用（PRD 阶段1 邮箱验证）。"""

import smtplib
from unittest.mock import Mock, patch

import pytest

from app.services.email_sender import EmailSenderError, send_verification_email


class TestSendVerificationEmail:
    def test_sends_code_with_subject_and_body(self, monkeypatch):
        sent = {}

        class FakeSMTP:
            def __init__(self, *a, **k):
                pass

            def login(self, *a, **k):
                pass

            def sendmail(self, from_addr, to_addrs, msg):
                sent["from"] = from_addr
                sent["to"] = to_addrs
                sent["msg"] = msg

            def quit(self):
                pass

        with patch("app.services.email_sender.smtplib.SMTP_SSL", FakeSMTP), patch(
            "app.services.email_sender.get_settings"
        ) as mock_cfg:
            mock_cfg.return_value = Mock(
                smtp_host="smtp.example.com",
                smtp_port=465,
                smtp_user="sender@example.com",
                smtp_password="secret",
                smtp_from="moutalk@example.com",
            )
            send_verification_email("user@example.com", "123456")

        from email import message_from_string

        assert sent["from"] == "moutalk@example.com"
        assert "user@example.com" in sent["to"]
        msg = message_from_string(sent["msg"])
        msg = message_from_string(sent["msg"])
        body = msg.get_payload()[0].get_payload(decode=True).decode("utf-8")
        assert "123456" in body
        assert "谋谈" in body

    def test_degrades_when_smtp_not_configured(self, monkeypatch):
        """SMTP 未配置（dev 默认）→ 不抛错，仅日志（注册流程不阻断）。"""
        monkeypatch.setattr(
            "app.services.email_sender.get_settings",
            lambda: Mock(smtp_host="", smtp_port=465, smtp_user="", smtp_password="", smtp_from=""),
        )
        send_verification_email("user@example.com", "123456")  # 不应抛异常

    def test_raises_when_send_fails(self, monkeypatch):
        class BoomSMTP:
            def __init__(self, *a, **k):
                raise smtplib.SMTPException("connect boom")

        with patch("app.services.email_sender.smtplib.SMTP_SSL", BoomSMTP), pytest.raises(
            EmailSenderError
        ):
            send_verification_email("user@example.com", "123456")


class TestIssueCodeSendsEmail:
    def test_issue_code_calls_sender(self, session):
        from app.services.auth import AuthService
        from app.services.email_sender import FakeEmailSender

        sender = FakeEmailSender()
        service = AuthService()
        code = service.issue_code(session, "alice@example.com", sender=sender)
        assert code
        assert sender.sent == [("alice@example.com", code)]

    def test_issue_code_fallback_to_logger_when_no_sender(self, session, capsys):
        """默认 sender（无 SMTP 配置时降级日志）不阻断验证码生成。"""
        from app.services.auth import AuthService

        code = AuthService().issue_code(session, "alice@example.com")
        assert len(code) == 6