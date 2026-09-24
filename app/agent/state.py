"""LangGraph 状态定义。"""
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    result: dict | None  # deliver 交付的原始结果（DeliverRequest）
    rendered: dict | None  # 前端渲染数据（summary + tables + charts）
