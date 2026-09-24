"""最终交付工具（Agent 结束信号）。"""
from langchain_core.tools import tool

from app.tools.models import DeliverRequest


@tool(args_schema=DeliverRequest)
def deliver(summary: str, tables: list[dict]) -> str:
    """交付最终分析结果：提交中文结论摘要与所有结果表格。调用本工具后本轮分析结束。"""
    return "已接收最终结果。"
