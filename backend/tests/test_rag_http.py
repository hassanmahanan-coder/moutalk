"""RAG http 模式（Milvus 完整版容器）集成测试（PRD 9.2）。

Milvus 完整版 insert 为异步写入：插入后必须 flush 才能被检索（与 Lite 同步语义不同）。
容器未运行时（CI/无 Docker）自动 skip；测试用独立 collection 名，结束即清理。
"""

import socket
from uuid import uuid4

import pytest

from app.services import rag
from app.services.rag import RAGMemory

HTTP_URI = "http://localhost:19530"


def _milvus_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 19530), timeout=2):
            return True
    except OSError:
        return False


needs_milvus = pytest.mark.skipif(
    not _milvus_up(), reason="Milvus http 容器未运行（需 docker compose up -d milvus-standalone）"
)


@needs_milvus
class TestRAGMemoryHttp:
    def test_add_round_immediately_searchable(self, monkeypatch):
        name = f"test_rag_http_{uuid4().hex[:8]}"
        monkeypatch.setattr(rag, "COLLECTION_NAME", name)
        memory = RAGMemory(HTTP_URI)
        memory.setup()
        try:
            memory.add_round("s1", "user", "你们的报价太高了")
            results = memory.search("s1", "太贵了能优惠吗", top_k=3)
            assert results, "插入后应立即可检索（需要 flush 语义）"
        finally:
            memory._ensured().drop_collection(name)
            memory.close()

    def test_search_scopes_by_scenario(self, monkeypatch):
        name = f"test_rag_http_{uuid4().hex[:8]}"
        monkeypatch.setattr(rag, "COLLECTION_NAME", name)
        memory = RAGMemory(HTTP_URI)
        memory.setup()
        try:
            memory.add_round("s1", "user", "服务器报价 200 万")
            memory.add_round("s2", "user", "服务器报价 200 万")
            results = memory.search("s1", "服务器报价", top_k=3)
            assert results
            assert all(r["scenario_id"] == "s1" for r in results)
        finally:
            memory._ensured().drop_collection(name)
            memory.close()
