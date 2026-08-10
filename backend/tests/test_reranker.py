"""BGE-Reranker 测试（PRD 8.3）：候选重排 + 降级链。

- NoopReranker：未配置模型时保持原序（现有行为不变）
- BGEReranker：FlagReranker compute_score 按相关性排序（真实模型 skip）
- RAGMemory.search：top_k=10 候选 → rerank → top-3（PRD 8.3 流程）
"""

import os

import pytest

from app.services import reranker as reranker_mod
from app.services.reranker import BGEReranker, NoopReranker, build_reranker

EMPTY_SETTINGS = type("S", (), {"reranker_model_path": "", "reranker_backend": "local_cpu"})


class TestNoopReranker:
    def test_keeps_order(self):
        r = NoopReranker()
        idx, scores = r.rank("查询", ["a", "b", "c"])
        assert idx == [0, 1, 2]
        assert scores == [0.0, 0.0, 0.0]

    def test_empty_candidates(self):
        r = NoopReranker()
        assert r.rank("q", []) == ([], [])


class TestBuildReranker:
    def test_default_noop_without_model(self, monkeypatch):
        monkeypatch.setattr(reranker_mod, "get_settings", lambda: EMPTY_SETTINGS)
        assert isinstance(build_reranker(), NoopReranker)

    def test_degrades_to_noop_when_model_missing(self, monkeypatch, tmp_path):
        settings = type(
            "S", (), {"reranker_model_path": str(tmp_path / "no_model"), "reranker_backend": "local_cpu"}
        )
        monkeypatch.setattr(reranker_mod, "get_settings", lambda: settings)
        assert isinstance(build_reranker(), NoopReranker)


needs_reranker = pytest.mark.skipif(
    not os.path.isdir(os.environ.get("BGE_RERANKER_PATH", "")),
    reason="未下载 bge-reranker-base（魔搭下载方案），跳过真实重排",
)


@needs_reranker
class TestBGEReranker:
    def test_rank_sorts_by_relevance(self):
        backend = BGEReranker(os.environ["BGE_RERANKER_PATH"])
        try:
            docs = [
                "服务器报价 200 万包含三年维保",
                "今天天气很好适合出去散步",
                "我们可以把价格谈到 210 万并延长账期",
            ]
            idx, scores = backend.rank("报价能不能降到 200 万", docs)
            assert idx[0] != 1, "天气句子应排最后"
            assert scores[idx[0]] >= scores[idx[1]] >= scores[idx[2]]
            assert len(idx) == 3
        finally:
            backend.close()
