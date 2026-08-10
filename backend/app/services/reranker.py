"""BGE-Reranker 重排层（PRD 8.3）：Milvus top-10 候选 → 重排 → top-3。

- BGEReranker：官方 FlagEmbedding `FlagReranker`，cross-encoder 逐对打分。
  模型路径：`settings.reranker_model_path`（本地目录，魔搭下载方案见 docs）。
- NoopReranker：模型未配置/不可用时保持原序（现有行为不变，零依赖）。
- 单例缓存：模块级实例复用，避免重复加载权重。
  Source: https://huggingface.co/BAAI/bge-reranker-base
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RerankerBackend(Protocol):
    """重排后端统一接口。"""

    def rank(self, query: str, candidates: list[str]) -> tuple[list[int], list[float]]: ...


class NoopReranker:
    """无模型降级：保持候选原序（与不接 reranker 行为一致）。"""

    def rank(self, query: str, candidates: list[str]) -> tuple[list[int], list[float]]:
        return list(range(len(candidates))), [0.0] * len(candidates)


class BGEReranker:
    """BGE-Reranker cross-encoder 重排（官方 FlagReranker，CPU 推理）。"""

    def __init__(self, model_path: str):
        self._model_path = model_path

    def _load(self):
        global _RERANKER_INSTANCE
        if _RERANKER_INSTANCE is not None:
            return _RERANKER_INSTANCE
        try:
            from FlagEmbedding import FlagReranker
        except ImportError as exc:
            logger.warning("FlagEmbedding 未安装，Reranker 不可用: %s", exc)
            raise RuntimeError("FlagEmbedding not installed") from exc
        _apply_tokenizer_compat()  # transformers 5.x 兼容层
        logger.info("加载 BGE-Reranker 模型（CPU，首次较慢）: %s", self._model_path)
        _RERANKER_INSTANCE = FlagReranker(self._model_path, use_fp16=False)
        return _RERANKER_INSTANCE

    def rank(self, query: str, candidates: list[str]) -> tuple[list[int], list[float]]:
        if not candidates:
            return [], []
        model = self._load()
        pairs = [[query, doc] for doc in candidates]
        scores = model.compute_score(pairs, normalize=True)
        if not isinstance(scores, list):
            scores = [scores]
        order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
        return order, [float(s) for s in scores]

    def close(self) -> None:
        pass  # 单例常驻内存


_RERANKER_INSTANCE = None
_TOKENIZER_COMPAT_APPLIED = False


def _apply_tokenizer_compat() -> None:
    """transformers 5.x 移除了 `prepare_for_model`，FlagEmbedding 1.4 仍依赖。

    等价实现：tokenizer(query, passage, ...) 的文本对模式返回同构 dict。
    Source: transformers 5 migration（BatchEncoding 替代 prepare_for_model）。
    """
    global _TOKENIZER_COMPAT_APPLIED
    if _TOKENIZER_COMPAT_APPLIED:
        return
    try:
        from transformers import XLMRobertaTokenizer

        if not hasattr(XLMRobertaTokenizer, "prepare_for_model"):
            def prepare_for_model(self, query, passage, truncation="only_second", max_length=512, padding=False):
                # transformers 5 移除 prepare_for_model：ids 列表还原为文本，用 fast
                # tokenizer 的文本对模式重新编码（等价 [CLS]q[SEP]p[SEP] 结构）
                q_text = self.decode(list(query), skip_special_tokens=True)
                p_text = self.decode(list(passage), skip_special_tokens=True)
                out = self(
                    [q_text],
                    [p_text],
                    return_tensors=None,
                    add_special_tokens=True,
                    truncation=truncation,
                    max_length=max_length,
                    padding=padding,
                )
                n = len(out["input_ids"][0])
                return {
                    "input_ids": out["input_ids"][0],
                    "attention_mask": out["attention_mask"][0],
                    "token_type_ids": [0] * n,  # XLMRoberta 无 segment 编码，全 0
                }

            XLMRobertaTokenizer.prepare_for_model = prepare_for_model
        _TOKENIZER_COMPAT_APPLIED = True
    except Exception as exc:  # noqa: BLE001 兼容层失败则由调用方降级
        logger.warning("Reranker tokenizer 兼容层应用失败: %s", exc)


def _is_model_available(path: str) -> bool:
    if not path:
        return False
    return os.path.isfile(os.path.join(path, "config.json"))


def build_reranker() -> RerankerBackend:
    """按配置构建重排后端；不可用静默降级 Noop（保持原序）。"""
    settings = get_settings()
    if settings.reranker_backend != "hash" and _is_model_available(settings.reranker_model_path):
        try:
            return BGEReranker(settings.reranker_model_path)
        except Exception as exc:  # noqa: BLE001 库缺失/加载失败降级
            logger.warning("BGE-Reranker 初始化失败，降级 Noop: %s", exc)
    return NoopReranker()
