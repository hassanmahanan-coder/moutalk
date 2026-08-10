"""Embedding 抽象层测试（PRD 8.3 / 9.2）：hash 降级 + BGE-M3 接入。

- hash backend：确定性、1024 维（对齐 BGE-M3 dense 维度）、归一化、零依赖
- BGE-M3 backend：模型路径不存在 / 库缺失时静默降级 hash（不阻断谈判）
- 真实 BGE-M3 推理（需手动下载模型）用 needs_bge_model 标记，模型缺失自动 skip
"""

import os

import pytest

from app.services import embeddings
from app.services.embeddings import (
    BGE_M3_DIM,
    HashEmbeddingBackend,
    build_embedding_backend,
)

EMPTY_SETTINGS = type("S", (), {"embedding_model_path": "", "embedding_backend": "local_cpu"})


class TestHashEmbeddingBackend:
    def test_deterministic(self):
        b = HashEmbeddingBackend()
        assert b.embed("报价 200 万可以吗") == b.embed("报价 200 万可以吗")

    def test_dimension_matches_bge_m3(self):
        b = HashEmbeddingBackend()
        assert len(b.embed("任意文本")) == BGE_M3_DIM == 1024

    def test_normalized(self):
        v = HashEmbeddingBackend().embed("任意文本")
        norm = sum(x * x for x in v) ** 0.5
        assert abs(norm - 1.0) < 1e-6

    def test_empty_text_zero_vector(self):
        v = HashEmbeddingBackend().embed("")
        assert all(x == 0 for x in v)

    def test_similar_texts_closer(self):
        b = HashEmbeddingBackend()
        a, b2, c = b.embed("能不能便宜一点"), b.embed("便宜点行不行"), b.embed("今天天气真好")
        assert sum(abs(x - y) for x, y in zip(a, b2)) < sum(abs(x - y) for x, y in zip(a, c))


class TestBuildEmbeddingBackend:
    def test_default_builds_hash_without_model(self, monkeypatch):
        """模型路径为空时直接 hash（零依赖可离线）。"""
        monkeypatch.setattr(embeddings, "get_settings", lambda: EMPTY_SETTINGS)
        backend = build_embedding_backend()
        assert isinstance(backend, HashEmbeddingBackend)

    def test_degrades_to_hash_when_model_missing(self, monkeypatch, tmp_path):
        """配置了路径但目录不存在（未下载）→ 降级 hash 不报错。"""
        settings = type(
            "S", (), {"embedding_model_path": str(tmp_path / "no_such_model"), "embedding_backend": "local_cpu"}
        )
        monkeypatch.setattr(embeddings, "get_settings", lambda: settings)
        backend = build_embedding_backend()
        assert isinstance(backend, HashEmbeddingBackend)


needs_bge_model = pytest.mark.skipif(
    not os.path.isdir(os.environ.get("BGE_M3_MODEL_PATH", "")),
    reason="未下载 BGE-M3 模型（见 docs：HF_ENDPOINT=hf-mirror 方案），跳过真实推理",
)


@needs_bge_model
class TestBGEM3Backend:
    def test_embed_returns_1024_dim(self):
        backend = embeddings.BGEM3EmbeddingBackend(os.environ["BGE_M3_MODEL_PATH"])
        try:
            v = backend.embed("服务器报价 200 万")
            assert len(v) == BGE_M3_DIM
        finally:
            backend.close()
