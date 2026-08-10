"""RAG 向量记忆测试：哈希 embedding 确定性、Milvus 存取、相似检索（PRD 8.3 / 9.2）。"""

from app.services.rag import RAGMemory, build_rag_memory, hash_embedding


class TestHashEmbedding:
    def test_deterministic(self):
        v1 = hash_embedding("报价 200 万可以吗")
        v2 = hash_embedding("报价 200 万可以吗")
        assert v1 == v2

    def test_similar_texts_are_close(self):
        a = hash_embedding("能不能便宜一点")
        b = hash_embedding("便宜点行不行")
        c = hash_embedding("今天天气真好")
        da = sum(abs(x - y) for x, y in zip(a, b))
        db = sum(abs(x - y) for x, y in zip(a, c))
        assert da < db, "相似文本向量距离应小于不相关文本"

    def test_dimension_and_normalization(self):
        v = hash_embedding("任意文本", dim=128)
        assert len(v) == 128
        norm = sum(x * x for x in v) ** 0.5
        assert abs(norm - 1.0) < 1e-6, "向量应归一化"

    def test_empty_text_returns_zero_vector(self):
        v = hash_embedding("")
        assert all(x == 0 for x in v)


class TestRAGMemory:
    def _make_memory(self, tmp_path) -> RAGMemory:
        uri = str(tmp_path / "rag.db")
        memory = RAGMemory(uri)
        memory.setup()
        return memory

    def test_add_and_search_roundtrip(self, tmp_path):
        memory = self._make_memory(tmp_path)
        memory.add_round("s1", "user", "你们的报价太高了")
        memory.add_round("s1", "assistant", "可以谈，450 万包含全部服务")
        results = memory.search("s1", "太贵了能优惠吗", top_k=3)
        assert results, "应检索到至少一条历史"
        assert all(r["scenario_id"] == "s1" for r in results)
        assert results[0]["distance"] >= results[-1]["distance"], "按相似度降序"

    def test_search_scopes_by_scenario(self, tmp_path):
        memory = self._make_memory(tmp_path)
        memory.add_round("s1", "user", "服务器报价 200 万")
        memory.add_round("s2", "user", "服务器报价 200 万")
        results = memory.search("s1", "服务器报价", top_k=3)
        assert results
        assert all(r["scenario_id"] == "s1" for r in results)

    def test_search_empty_scenario_returns_empty(self, tmp_path):
        memory = self._make_memory(tmp_path)
        memory.add_round("s1", "user", "hello")
        assert memory.search("ghost", "hello", top_k=3) == []

    def test_top_k_respected(self, tmp_path):
        memory = self._make_memory(tmp_path)
        for i in range(6):
            memory.add_round("s1", "user", f"第 {i} 轮报价试" + "样" * i)
        results = memory.search("s1", "报价", top_k=3)
        assert len(results) <= 3


class TestBuildRAGMemory:
    def test_build_from_settings(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.services.rag.get_settings",
            lambda: type("S", (), {"milvus_uri": str(tmp_path / "cfg.db")})(),
        )
        memory = build_rag_memory()
        assert isinstance(memory, RAGMemory)
        memory.close()