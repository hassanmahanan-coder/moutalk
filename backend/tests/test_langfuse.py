"""LangFuse 观测集成测试：handler 按配置启用/禁用（PRD 9.6 token 监控）。"""

import os
from unittest.mock import patch

from app.engine.llm import build_langfuse_handler


class TestBuildLangfuseHandler:
    def test_returns_none_when_keys_missing(self):
        with patch.dict(
            os.environ,
            {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "", "LANGFUSE_HOST": ""},
            clear=False,
        ):
            assert build_langfuse_handler() is None

    def test_returns_none_when_only_public_key(self):
        with patch.dict(
            os.environ,
            {"LANGFUSE_PUBLIC_KEY": "pk-test", "LANGFUSE_SECRET_KEY": ""},
            clear=False,
        ):
            assert build_langfuse_handler() is None

    def test_returns_handler_when_keys_present(self):
        with patch.dict(
            os.environ,
            {
                "LANGFUSE_PUBLIC_KEY": "pk-test",
                "LANGFUSE_SECRET_KEY": "sk-test",
                "LANGFUSE_HOST": "http://localhost:3000",
            },
            clear=False,
        ):
            handler = build_langfuse_handler()
            assert handler is not None
            from langfuse.langchain import CallbackHandler

            assert isinstance(handler, CallbackHandler)
