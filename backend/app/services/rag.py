"""RAG 向量记忆（PRD 8.3 / 9.2）：历史谈判片段存取 + 相似检索。

- embedding：抽象层 `app/services/embeddings.py`。首选 BGE-M3（1024 维，本地模型）；
  未配置/不可用时降级确定性 n-gram 哈希签名向量（同 1024 维，可离线测试）。
  `hash_embedding` 保留为兼容导出（等价 HashEmbeddingBackend）。
- 存储：Milvus（`settings.milvus_uri`，本地文件 milvus.db / 完整版 http 地址均可），
  collection `negotiation_history`。
- 检索：COSINE 相似度 top-k，按距离降序返回。
- 维度升级：collection 维度与当前 embedding 维度（BGE_M3_DIM=1024）不匹配时自动
  drop 重建（开发数据可弃；记录日志）。旧 128 维 hash 数据在升级时清空。

注意：pymilvus 3.x 在 import 时自动 `load_dotenv()`。`.env` 的 MILVUS_URI 必须是
合法格式（本地 `*.db` 文件路径或 `http(s)://` 连接串），否则模块加载期抛
ConnectionConfigException。不要在此清空环境变量：pydantic-settings 的优先级
env > .env 文件，清空会导致 `settings.milvus_uri` 读到空串。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pymilvus import MilvusClient

from app.core.config import get_settings
from app.services.embeddings import (
    DIM as _HASH_DIM,
)
from app.services.embeddings import (
    EmbeddingBackend,
    HashEmbeddingBackend,
    build_embedding_backend,
    hash_embedding,  # 兼容导出（等价 HashEmbeddingBackend）
)
from app.services.reranker import NoopReranker, RerankerBackend, build_reranker

logger = logging.getLogger(__name__)

COLLECTION_NAME = "negotiation_history"
RERANK_CANDIDATES = 10  # PRD 8.3：Milvus 候选数，reranker 精排后取 top_k


def _normalize_uri(uri: str) -> str:
    """兼容 pymilvus 2.x 旧格式（milvus:///./xxx.db）→ 本地文件路径。"""
    if uri.startswith("milvus:///"):
        return uri[len("milvus:///") :]
    return uri


def _embedding_dim(embedder: EmbeddingBackend) -> int:
    """embedding 维度：BGE 后端从模型 config 读取（512/1024 自适应），hash 用默认。"""
    dim = getattr(embedder, "dim", None)
    if callable(dim):
        try:
            return int(dim())
        except Exception as exc:  # noqa: BLE001 维度读取失败回退默认
            logger.warning("embedding 维度读取失败，回退默认 %s: %s", _HASH_DIM, exc)
    return _HASH_DIM


def build_rag_memory(
    embedder: EmbeddingBackend | None = None,
    reranker: RerankerBackend | None = None,
) -> RAGMemory:
    """构建 RAG 记忆：Milvus + embedding 后端 + reranker 重排（PRD 8.3）。

    不传 embedder/reranker 时按配置构建（BGE/hash 降级、BGE-Reranker/Noop 降级）；
    不可用抛异常由调用方降级。
    """
    memory = RAGMemory(
        _normalize_uri(get_settings().milvus_uri),
        embedder=embedder if embedder is not None else build_embedding_backend(),
        reranker=reranker if reranker is not None else build_reranker(),
    )
    memory.setup()
    return memory


class RAGMemory:
    """谈判历史向量记忆（Milvus 文件/服务器存储 + 可插拔 embedding + reranker）。"""

    def __init__(
        self,
        uri: str | os.PathLike[str],
        embedder: EmbeddingBackend | None = None,
        reranker: RerankerBackend | None = None,
    ):
        self._uri = str(uri)
        self._client: MilvusClient | None = None
        self._embedder = embedder if embedder is not None else HashEmbeddingBackend()
        self._reranker = reranker if reranker is not None else NoopReranker()

    def _ensured(self) -> MilvusClient:
        if self._client is None:
            self._client = MilvusClient(self._uri)
        return self._client

    def _dim(self) -> int:
        return _embedding_dim(self._embedder)

    def setup(self) -> None:
        client = self._ensured()
        dim = self._dim()
        if client.has_collection(COLLECTION_NAME):
            schema = client.describe_collection(COLLECTION_NAME)
            existing_dim = None
            for field in schema.get("fields", []):
                if field.get("name") == "vector":
                    existing_dim = field.get("params", {}).get("dim")
                    break
            if existing_dim != dim:
                logger.warning(
                    "collection %s 维度 %s != 当前 %s，drop 重建（旧数据弃）",
                    COLLECTION_NAME,
                    existing_dim,
                    dim,
                )
                client.drop_collection(COLLECTION_NAME)
        if not client.has_collection(COLLECTION_NAME):
            client.create_collection(
                collection_name=COLLECTION_NAME,
                dimension=dim,
                auto_id=True,
                metric_type="COSINE",
            )

    def add_round(self, scenario_id: str, role: str, text: str) -> None:
        if not text.strip():
            return
        vector = self._embedder.embed(text)
        if not any(vector):
            return
        self._ensured().insert(
            COLLECTION_NAME,
            {
                "vector": vector,
                "scenario_id": scenario_id,
                "role": role,
                "text": text,
            },
        )
        # Milvus 完整版 insert 异步落盘：flush 后立即可检索（Lite 同步语义下无副作用）。
        self._ensured().flush(COLLECTION_NAME)

    def search(self, scenario_id: str, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        vector = self._embedder.embed(query)
        if not any(vector):
            return []
        try:
            # PRD 8.3：Milvus 先取 top-10 候选（宽松召回），reranker 精排后取 top_k
            res = self._ensured().search(
                COLLECTION_NAME,
                data=[vector],
                limit=max(top_k * 3, RERANK_CANDIDATES),
                filter=f'scenario_id == "{scenario_id}"',
                output_fields=["text", "role", "scenario_id"],
            )
        except Exception:  # noqa: BLE001 collection 不存在/未建则空结果
            return []
        hits = (res or [[]])[0]
        if not hits:
            return []
        candidates = [
            {
                "text": hit["entity"].get("text", ""),
                "role": hit["entity"].get("role", ""),
                "scenario_id": hit["entity"].get("scenario_id", ""),
                "distance": float(hit.get("distance", 0.0)),
            }
            for hit in hits
        ]
        # BGE-Reranker 重排（Noop 时保持原序）
        order, _ = self._reranker.rank(
            query,
            [c["text"] for c in candidates],
        )
        ranked = [candidates[i] for i in order if i < len(candidates)]
        return ranked[:top_k]

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


__all__ = [
    "COLLECTION_NAME",
    "RAGMemory",
    "build_embedding_backend",
    "build_rag_memory",
    "hash_embedding",
]
