"""知识检索工具：query_knowledge。

让 Agent 在分析前检索数据集的领域知识（字段口径、业务背景、分析建议），
解决 LLM 对"这个字段怎么解读、这个数据集适用什么分析"记忆不足的问题——即 RAG。
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from app.knowledge.retriever import retrieve

logger = logging.getLogger(__name__)


@tool
def query_knowledge(question: str) -> str:
    """检索数据集的领域知识（字段口径、业务背景、分析建议），返回最相关的知识文本。

    当用户问题涉及特定数据集/字段的业务含义，或你不确定某列/某场景怎么分析时，
    先调用此工具检索背景知识，再据此执行 analyze_data。
    """
    try:
        hits = retrieve(question, top_k=2)
        if not hits:
            return json.dumps({"matches": [], "note": "未检索到相关知识，请基于 list_datasets 的字段说明分析。"}, ensure_ascii=False)
        return json.dumps({"matches": hits}, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        logger.exception("query_knowledge 失败")
        return json.dumps({"error": str(e)}, ensure_ascii=False)