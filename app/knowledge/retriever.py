"""知识检索器：query_knowledge 工具的核心。

采用混合检索，保证 embedding 端点不可用时也能工作：
1) 向量检索（可选）：若配置了 OpenAI 兼容 embedding 端点则用 FAISS 语义检索；
2) 关键词兜底：按 token 共现度匹配 KNOWLEDGE_DOCS，零额外依赖，最稳。
"""
from __future__ import annotations

import math
import re
from typing import Any

from app.knowledge import KNOWLEDGE_DOCS, KnowledgeDoc

# 通用中文停用词（可扩充）
_STOP = set("的了在是在与和或这那那个一个数据我要你他她它们分析请分别展示如何什么怎么帮助".split())

_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-龥]{1,4}", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    """中文 + 英文/数值混合分词。"""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t and t not in _STOP]


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def keyword_search(query: str, top_k: int = 2) -> list[tuple[KnowledgeDoc, float]]:
    """基于关键词共现的确定性检索。"""
    q_tokens = set(_tokenize(query))
    scored: list[tuple[KnowledgeDoc, float]] = []
    for doc in KNOWLEDGE_DOCS:
        # 同时考虑文本内容与显式 keywords
        doc_text = doc.title + " " + doc.content + " " + " ".join(doc.keywords)
        doc_tokens = set(_tokenize(doc_text))
        score = _jaccard(q_tokens, doc_tokens)
        # 显式 keywords 命中加成（业务领域名/专有名词）
        kw_hits = [k for k in doc.keywords if k.lower() in query.lower()]
        if kw_hits:
            score += 0.3 * len(kw_hits) / max(1, len(doc.keywords))
        if score > 0:
            scored.append((doc, score))
    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]


def retrieve(query: str, top_k: int = 2) -> list[str]:
    """检索最相关的知识文档文本。优先向量检索失败则以关键词兜底。"""
    try:
        vector_hits = _vector_search(query, top_k)
        if vector_hits:
            return [d[0] for d in vector_hits]
    except Exception:  # noqa: BLE001  embedding 不可用时静默回退
        pass
    hits = keyword_search(query, top_k)
    return [f"[{doc.title}]\n{doc.content}" for doc, _ in hits]


# ---------- 向量检索（可选） ----------
_INDEX: Any = None
_EMBEDDER: Any = None


def _get_cache_path() -> str:
    import os
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    return str(root / "app" / "data" / "knowledge_cache" / "index.faiss")


def _init_embedder() -> Any:
    """按需初始化 OpenAI 兼容 embedding 器（配置了 embedding 端点时）。"""
    global _EMBEDDER
    if _EMBEDDER is not None:
        return _EMBEDDER
    from langchain_openai import OpenAIEmbeddings

    from app.config import settings

    # 仅当显式配置了 embedding 端点/APIKey 时才走向量检索
    base_url = getattr(settings, "embedding_base_url", "") or ""
    api_key = getattr(settings, "embedding_api_key", "") or settings.openai_api_key
    if not base_url:
        return None
    _EMBEDDER = OpenAIEmbeddings(model=getattr(settings, "embedding_model", "text-embedding-ada-002"), base_url=base_url, api_key=api_key or None)
    return _EMBEDDER


def _vector_search(query: str, top_k: int = 2) -> list[tuple[str, float]]:
    """FAISS 向量检索；构建索引一次缓存到本地。"""
    global _INDEX
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document

    embedder = _init_embedder()
    if embedder is None:
        return []

    cache_path = _get_cache_path()
    try:
        if _INDEX is None:
            _INDEX = FAISS.load_local(cache_path, embedder, allow_dangerous_deserialization=True)
    except Exception:  # noqa: BLE001
        docs = [Document(page_content=f"[{d.title}]\n{d.content}", metadata={"title": d.title}) for d in KNOWLEDGE_DOCS]
        _INDEX = FAISS.from_documents(docs, embedder)
        try:
            _INDEX.save_local(cache_path)
        except Exception:  # noqa: BLE001
            pass
    results = _INDEX.similarity_search_with_score(query, k=top_k)
    return [(doc.page_content.split("\n", 1)[-1], float(score)) for doc, score in results]