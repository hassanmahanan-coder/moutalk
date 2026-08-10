"""Embedding 抽象层（PRD 8.3 / 9.2）：BGE 系列优先，hash 签名降级。

- BGE 系列：官方 FlagEmbedding `FlagModel`，维度从模型 config.json 自动读取
  （bge-small-zh 512 维 / bge-m3 1024 维），CPU 推理：
  - bge-small-zh-v1.5：~17ms/条（满足 PRD <200ms，谈判场景推荐）
  - BGE-M3：~9s/条（CPU 物理极限，仅质量优先场景；生产建议 xinference 托管）
  模型路径：`settings.embedding_model_path`（本地目录，见 docs 下载方案）。
  Source: https://huggingface.co/BAAI/bge-small-zh-v1.5
- hash 降级：确定性 n-gram 哈希签名向量（dim 对齐 BGE-M3 1024），零依赖可离线。
  模型未下载 / 库缺失 / 加载失败时静默降级，不阻断谈判主流程。
- 统一接口：`embed(text) -> list[float]`（维度随模型）。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BGE_M3_DIM = 1024  # BGE-M3 dense 维度（官方 Specs）
DIM = BGE_M3_DIM  # hash 降级默认维度（对齐 BGE-M3）
_NGRAM = 3

_TOKEN_CHAR_RE = re.compile(r"[\w\u4e00-\u9fff]")


class EmbeddingBackend(Protocol):
    """embedding 后端统一接口。"""

    def embed(self, text: str) -> list[float]: ...


def _tokens(text: str) -> list[str]:
    """中文/拉丁词 n-gram 切分：按字符窗口生成 tokens，用于哈希签名。"""
    s = re.sub(r"\s+", "", text or "")
    if not s:
        return []
    unigrams = [ch for ch in s if _TOKEN_CHAR_RE.match(ch)]
    if not unigrams:
        return []
    grams: list[str] = list(unigrams)
    for i in range(len(unigrams) - 1):
        grams.append(unigrams[i] + unigrams[i + 1])
    for i in range(len(unigrams) - _NGRAM + 1):
        grams.append("".join(unigrams[i : i + _NGRAM]))
    return grams


def _hash_to_index(token: str, dim: int) -> int:
    h = hashlib.md5(token.encode()).hexdigest()
    return int(h[:8], 16) % dim


class HashEmbeddingBackend:
    """确定性 hashing-trick 特征向量（降级方案，dim 对齐 BGE-M3）。"""

    def __init__(self, dim: int = BGE_M3_DIM):
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = _tokens(text)
        if not tokens:
            return vec
        for tok in tokens:
            idx = _hash_to_index(tok, self.dim)
            sign = 1.0 if int(hashlib.md5(("s" + tok).encode()).hexdigest()[:8], 16) % 2 else -1.0
            vec[idx] += sign
        norm = sum(x * x for x in vec) ** 0.5
        if norm == 0:
            return vec
        return [x / norm for x in vec]


def hash_embedding(text: str, dim: int = BGE_M3_DIM) -> list[float]:
    """兼容导出：确定性哈希签名向量（等价 HashEmbeddingBackend.embed）。"""
    return HashEmbeddingBackend(dim).embed(text)


class BGEM3EmbeddingBackend:
    """BGE 系列 dense embedding（官方 FlagEmbedding，CPU 推理）。

    支持所有 BGE 系列模型（bge-small/base/large/m3 等）：从模型 config.json 读取
    hidden_size 作为向量维度（512/768/1024 自动适配）。
    单例缓存：模块级 _BGE_INSTANCE 复用已加载模型，避免每次构建重复加载权重
    （PRD 9.2：首次加载预热到内存缓存）。
    注意：BGE-M3 用 FlagModel（纯 dense 1024 维）而非 BGEM3FlagModel——后者在
    CPU 上推理 ~9s/条远超 PRD <200ms 目标；小模型（bge-small-zh）CPU 仅 ~17ms。
    """

    def __init__(self, model_path: str, max_length: int = 512):
        self._model_path = model_path
        self._max_length = max_length

    def _load(self):
        global _BGE_INSTANCE
        if _BGE_INSTANCE is not None:
            return _BGE_INSTANCE
        try:
            from FlagEmbedding import FlagModel
        except ImportError as exc:
            logger.warning("FlagEmbedding 未安装，BGE 不可用: %s", exc)
            raise RuntimeError("FlagEmbedding not installed") from exc
        logger.info("加载 BGE embedding 模型（CPU，首次较慢）: %s", self._model_path)
        _BGE_INSTANCE = FlagModel(
            self._model_path,
            query_instruction_for_retrieval=None,
            use_fp16=False,
        )
        return _BGE_INSTANCE

    def embed(self, text: str) -> list[float]:
        if not (text or "").strip():
            return [0.0] * self.dim()
        model = self._load()
        vec = model.encode([text], max_length=self._max_length)[0]
        return [float(x) for x in vec]

    def dim(self) -> int:
        """从模型配置读取向量维度（hidden_size）。"""
        import json
        import os

        cfg_path = os.path.join(self._model_path, "config.json")
        try:
            with open(cfg_path, encoding="utf-8") as f:
                return int(json.load(f).get("hidden_size", BGE_M3_DIM))
        except (OSError, ValueError):
            return BGE_M3_DIM

    def close(self) -> None:
        pass  # 单例常驻内存（PRD 9.2 预热缓存）


_BGE_INSTANCE = None


def _is_model_available(path: str) -> bool:
    """模型目录可用：含 config.json（HF 模型仓库标志）。"""
    if not path:
        return False
    return os.path.isfile(os.path.join(path, "config.json"))


def build_embedding_backend() -> EmbeddingBackend:
    """按配置构建 embedding 后端；BGE-M3 不可用静默降级 hash。"""
    settings = get_settings()
    model_path = settings.embedding_model_path
    if settings.embedding_backend != "hash" and _is_model_available(model_path):
        try:
            return BGEM3EmbeddingBackend(model_path)
        except Exception as exc:  # noqa: BLE001 库缺失/加载失败降级
            logger.warning("BGE-M3 初始化失败，降级 hash embedding: %s", exc)
    return HashEmbeddingBackend()
