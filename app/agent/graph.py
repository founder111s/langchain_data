"""LangGraph 数据分析 Agent 图。

图结构:
    START -> agent -> tools -> (deliver 后) output -> END
                     └── 无工具调用时直接 output
"""
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.agent.deliver_tool import deliver
from app.agent.nodes import agent_node, output_node, run_tools_node
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.tools.analysis_tool import analyze_data
from app.tools.data_tools import list_datasets, select_dataset
from app.tools.knowledge_tool import query_knowledge

logger = logging.getLogger(__name__)

AGENT_TOOLS = [query_knowledge, list_datasets, select_dataset, analyze_data, deliver]
_TOOLS_BY_NAME = {t.name: t for t in AGENT_TOOLS}


def build_graph(llm):
    """构建并编译 LangGraph。llm 为 ChatOpenAI 实例。"""
    llm_with_tools = llm.bind_tools(AGENT_TOOLS)
    builder = StateGraph(AgentState)

    builder.add_node("agent", lambda state: agent_node(state, llm_with_tools))
    builder.add_node("tools", lambda state: run_tools_node(state, _TOOLS_BY_NAME))
    builder.add_node("output", output_node)

    builder.add_edge(START, "agent")

    def after_agent(state: dict) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "tools"
        return "output"

    def after_tools(state: dict) -> str:
        return "output" if state.get("result") else "agent"

    builder.add_conditional_edges("agent", after_agent, {"tools": "tools", "output": "output"})
    builder.add_conditional_edges("tools", after_tools, {"output": "output", "agent": "agent"})
    builder.add_edge("output", END)
    return builder.compile()


def run_analysis(question: str, llm, history: list[dict] | None = None) -> dict:
    """执行一次数据分析，返回 rendered 渲染数据。

    history: 可选的多轮对话历史，形如 [{"role": "user"|"assistant", "content": str}, ...]，
        用于让 Agent 理解上文（如"刚才那个国家再细分一下"）。assistant 的 content 传入其 summary 文本即可。

    返回结构: {"summary": str, "tables": [TableResult dict], "charts": [plotly dict]}
    """
    messages: list = [SystemMessage(content=SYSTEM_PROMPT)]
    if history:
        for m in history:
            role = m.get("role")
            text = str(m.get("content", "")).strip()
            if not text:
                continue
            if role == "user":
                messages.append(HumanMessage(content=text))
            elif role == "assistant":
                messages.append(AIMessage(content=text))
    messages.append(HumanMessage(content=question))

    graph = build_graph(llm)
    state = graph.invoke(
        {
            "messages": messages,
            "result": None,
            "rendered": None,
        },
        config={"recursion_limit": 40, "run_name": f"agent:{question[:30]}"},
    )
    rendered = state.get("rendered") or {"summary": "Agent 未返回结果。", "tables": [], "charts": []}
    return rendered
