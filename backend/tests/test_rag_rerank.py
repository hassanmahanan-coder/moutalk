"""RAG search + Reranker 集成测试（PRD 8.3）：top-10 候选 → 重排 → top-3。"""

from app.services.rag import RAGMemory


class FakeReranker:
    """固定排序的假 reranker：把候选逆序（验证 search 确实应用了 rerank 顺序）。"""

    def __init__(self):
        self.queries = []

    def rank(self, query, candidates):
        self.queries.append(query)
        order = list(range(len(candidates)))
        order.reverse()
        return order, [1.0] * len(candidates)


class TestRAGSearchWithReranker:
    def test_reranker_order_applied(self, tmp_path):
        memory = RAGMemory(str(tmp_path / "rag.db"), reranker=FakeReranker())
        memory.setup()
        for i in range(6):
            memory.add_round("s1", "user", f"第 {i} 轮报价" + "样" * i)
        memory.close()

        memory = RAGMemory(str(tmp_path / "rag.db"), reranker=FakeReranker())
        memory.setup()
        results = memory.search("s1", "报价", top_k=3)
        assert len(results) == 3
        # FakeReranker 逆序：索引 5 应排第一
        assert "第 5 轮" in results[0]["text"]
        memory.close()

    def test_reranker_receives_query(self, tmp_path):
        fake = FakeReranker()
        memory = RAGMemory(str(tmp_path / "rag.db"), reranker=fake)
        memory.setup()
        memory.add_round("s1", "user", "hello")
        memory.search("s1", "太贵了", top_k=2)
        assert fake.queries == ["太贵了"]
        memory.close()

    def test_noop_keeps_milvus_order(self, tmp_path):
        memory = RAGMemory(str(tmp_path / "rag.db"))  # 默认 Noop
        memory.setup()
        memory.add_round("s1", "user", "服务器报价 200 万")
        memory.add_round("s1", "user", "今天天气很好")
        results = memory.search("s1", "服务器报价", top_k=2)
        assert results
        assert results[0]["text"] == "服务器报价 200 万", "Noop 保持 Milvus 原序"
        memory.close()
