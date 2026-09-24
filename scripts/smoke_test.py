"""冒烟测试：不依赖 LLM 验证 数据加载 / 分析工具 / 图表生成 / 图编排。

用法:
    python scripts/smoke_test.py          # 工具链路（无 LLM）
    python scripts/smoke_test.py --llm "各国家销售额对比"   # 真实 LLM 全链路（需 .env 配置）
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import setup_logging  # noqa: E402

setup_logging()

CASES = [
    dict(dataset="ecommerce", operation="time_trend", value_col="Revenue", date_col="InvoiceDate", agg="sum", freq="M"),
    dict(dataset="ecommerce", operation="groupby_agg", group_by="Country", value_col="Revenue", agg="sum", top=5),
    dict(dataset="finance", operation="grouped_trend", group_by="Ticker", value_col="Close", date_col="Date", agg="mean", freq="W"),
    dict(dataset="finance", operation="time_trend", value_col="Close", date_col="Date", agg="mean", freq="W", where_col="Ticker", where_value="AAPL"),
    dict(dataset="climate", operation="time_trend", value_col="tmax", date_col="Date", agg="mean", freq="M", where_col="City", where_value="Beijing"),
    dict(dataset="health", operation="grouped_trend", group_by="location", value_col="new_cases", date_col="date", agg="sum", freq="M"),
]


def test_pipeline() -> None:
    from app.data.loader import load_all_meta, load_dataset
    from app.tools.analysis_tool import execute_analysis
    from app.tools.chart_tool import table_to_plotly
    from app.tools.models import AnalysisRequest, TableResult

    metas = load_all_meta()
    print(f"[OK] 数据集元信息: {[m['name'] for m in metas]}")

    for name in ["ecommerce", "finance", "climate", "health"]:
        df = load_dataset(name)
        assert len(df) > 0, f"{name} 为空"
        print(f"[OK] 加载 {name}: {df.shape}")

    for params in CASES:
        req = AnalysisRequest(**params)
        result = execute_analysis(load_dataset(req.dataset), req)
        assert result["rows"], f"空结果: {params}"
        tr = TableResult(**result)
        fig = table_to_plotly(tr)
        assert fig.get("data"), f"图表为空: {params['operation']}"
        print(f"[OK] {result['title']}: {len(result['rows'])} 行, chart={result['chart_type']}")


def test_graph_fake() -> None:
    """用确定性 Fake LLM 验证 LangGraph 全链路（工具执行 + deliver + 渲染）。"""
    from langchain_core.messages import AIMessage, ToolMessage

    from app.agent.graph import build_graph
    from app.agent.prompts import SYSTEM_PROMPT

    class FakeLLM:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages, **kwargs):
            n_tool = sum(1 for m in messages if isinstance(m, ToolMessage))
            n_ai = sum(1 for m in messages if isinstance(m, AIMessage))
            if n_tool == 0:
                return AIMessage(content="", tool_calls=[{"name": "list_datasets", "args": {}, "id": "1", "type": "tool_call"}])
            if n_tool == 1:
                return AIMessage(content="", tool_calls=[{"name": "select_dataset", "args": {"name": "ecommerce"}, "id": "2", "type": "tool_call"}])
            if n_tool == 2:
                return AIMessage(content="", tool_calls=[
                    {"name": "analyze_data", "args": {"dataset": "ecommerce", "operation": "groupby_agg", "group_by": "Country", "value_col": "Revenue", "agg": "sum", "top": 5}, "id": "3", "type": "tool_call"}
                ])
            if n_tool == 3:
                last_tool = next(m for m in reversed(messages) if isinstance(m, ToolMessage))
                table = json.loads(last_tool.content)
                return AIMessage(content="", tool_calls=[
                    {"name": "deliver", "args": {"summary": "冒烟测试总结", "tables": [table]}, "id": "4", "type": "tool_call"}
                ])
            return AIMessage(content="完成", tool_calls=[])

    graph = build_graph(FakeLLM())
    state = graph.invoke(
        {"messages": [AIMessage(content=SYSTEM_PROMPT)], "result": None, "rendered": None},
        config={"recursion_limit": 40},
    )
    rendered = state.get("rendered")
    assert rendered and rendered["tables"] and rendered["charts"], f"渲染数据不完整: {rendered}"
    print(f"[OK] 图链路: summary={rendered['summary']}, tables={len(rendered['tables'])}, charts={len(rendered['charts'])}")


def test_llm(question: str) -> None:
    from app.agent.graph import run_analysis
    from app.llm import get_llm

    llm = get_llm()
    rendered = run_analysis(question, llm)
    print(json.dumps({"summary": rendered["summary"], "n_tables": len(rendered["tables"]), "n_charts": len(rendered["charts"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if "--llm" in sys.argv:
        idx = sys.argv.index("--llm")
        question = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else "各国家销售额对比"
        test_llm(question)
    else:
        test_pipeline()
        test_graph_fake()
        print("冒烟测试全部通过")
