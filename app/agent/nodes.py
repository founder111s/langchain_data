"""LangGraph 节点：agent / run_tools / output。"""
import logging

from langchain_core.messages import AIMessage, ToolMessage

from app.tools.chart_tool import table_to_plotly
from app.tools.models import DeliverRequest, TableResult

logger = logging.getLogger(__name__)


def agent_node(state: dict, llm_with_tools):
    """LLM 节点：调用绑定工具的模型。"""
    resp = llm_with_tools.invoke(state["messages"])
    return {"messages": [resp]}


def run_tools_node(state: dict, tools_by_name: dict) -> dict:
    """工具节点：执行普通工具，拦截 deliver 并把交付物写入 state.result。"""
    last = state["messages"][-1]
    outputs: list = []
    delivered: dict | None = None

    for tc in last.tool_calls:
        name = tc["name"]
        args = tc.get("args") or {}
        if name == "deliver":
            try:
                delivered = DeliverRequest(**args).model_dump()
            except Exception as e:  # noqa: BLE001
                outputs.append(ToolMessage(content=f"deliver 参数校验失败: {e}", tool_call_id=tc.get("id", "")))
            continue
        tool = tools_by_name.get(name)
        if tool is None:
            outputs.append(ToolMessage(content=f"未知工具: {name}", tool_call_id=tc.get("id", "")))
            continue
        try:
            content = tool.invoke(args)
        except Exception as e:  # noqa: BLE001
            logger.exception("工具 %s 执行失败", name)
            content = f"工具执行失败: {e}"
        outputs.append(ToolMessage(content=content, tool_call_id=tc.get("id", "")))

    return {"messages": outputs, "result": delivered}


def _is_rate_col(values: list) -> bool:
    """判断某一列是否比率类（值均落在 [0,1]）。"""
    if not values:
        return False
    for v in values:
        if v is None:
            continue
        if not isinstance(v, (int, float)) or not (0 <= float(v) <= 1):
            return False
    return True


def _is_count_col(values: list) -> bool:
    """判断某一列是否计数类（值均为非负整数）。"""
    if not values:
        return False
    for v in values:
        if v is None:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or float(v) != int(v) or float(v) < 0:
            return False
    return True


def _key_col(table: TableResult) -> str | None:
    """返回表的"分组/索引键列名"。groupby 表首列即分组列，index_name 表则是索引列。"""
    if table.index_name:
        return table.index_name
    return table.columns[0] if table.columns else None


def _merge_dual_metric(tables: list[TableResult]) -> list[TableResult]:
    """合并"共享同一分组列 + 一张计数表、一张比率表"的多张表为一个双 Y 轴表格。

    当 LLM 未使用 value_col2 双聚合、而是拆成 count 表和 rate 表两张单轴图表时，
    此兜底逻辑把它们合成一张：柱状图(count, 左轴) + 折线(rate, 右轴)。
    """
    groups: dict[str, list[TableResult]] = {}
    for t in tables:
        k = _key_col(t)
        if k:
            groups.setdefault(k, []).append(t)

    merged: list[TableResult] = []
    used_idx_names: set[str] = set()

    for idx, members in groups.items():
        if len(members) < 2:
            continue
        # 收集各自的单一数值列（排除分组键列本身）
        count_t = rate_t = None
        count_col = rate_col = None
        for m in members:
            num_cols = [c for c in m.columns if c != idx]
            if len(num_cols) != 1:
                continue
            ci = m.columns.index(num_cols[0])
            vals = [r[ci] for r in m.rows]
            if _is_count_col(vals) and count_t is None:
                count_t, count_col = m, num_cols[0]
            elif _is_rate_col(vals) and rate_t is None:
                rate_t, rate_col = m, num_cols[0]

        if not (count_t and rate_t):
            continue

        c_ci = count_t.columns.index(count_col)
        r_ci = rate_t.columns.index(rate_col)
        # 若两张表数值列同名，需重命名以避免 chart_cols/y2_cols 冲突
        out_count_col, out_rate_col = count_col, rate_col
        if count_col == rate_col:
            out_count_col = f"{count_col}_count"
            out_rate_col = f"{rate_col}_rate"
        count_by = {r[0]: r[c_ci] for r in count_t.rows}
        rate_by = {r[0]: r[r_ci] for r in rate_t.rows}
        keys = sorted(set(count_by) & set(rate_by), key=lambda k: (k is None, str(k)))
        if not keys:
            continue
        rows = [[k, count_by[k], rate_by[k]] for k in keys]
        merged.append(
            TableResult(
                title=f"{idx} 对比（人数 + 比率）",
                columns=[idx, out_count_col, out_rate_col],
                index_name=idx,
                rows=rows,
                chart_type="bar",
                chart_cols=[out_count_col],
                y2_cols=[out_rate_col],
                note="由 count/rate 两张表合并为双 Y 轴图",
            )
        )
        used_idx_names.update(m.index_name or (m.columns[0] if m.columns else "") for m in members)

    # 保留未参与合并的表
    out = [t for t in tables if (_key_col(t) or "") not in used_idx_names]
    out.extend(merged)
    return out


def output_node(state: dict) -> dict:
    """输出节点：将交付结果渲染为前端可用的 summary + tables + charts。"""
    try:
        result = state.get("result")
        if not result:
            last = state["messages"][-1] if state.get("messages") else None
            text = (
                last.content
                if isinstance(last, AIMessage) and not getattr(last, "tool_calls", None)
                else "Agent 未产出结构化结果。"
            )
            return {"rendered": {"summary": str(text), "tables": [], "charts": []}}

        raw_tables = [TableResult(**t) for t in result.get("tables", [])]
        tables: list[TableResult] = _merge_dual_metric(raw_tables)

        rendered_tables, charts = [], []
        for tr in tables:
            rendered_tables.append(tr.model_dump())
            if tr.chart_type != "none":
                charts.append(table_to_plotly(tr))
        return {"rendered": {"summary": result.get("summary", ""), "tables": rendered_tables, "charts": charts}}
    except Exception as e:  # noqa: BLE001
        logger.exception("output_node 渲染失败")
        return {"rendered": {"summary": f"结果解析失败: {e}", "tables": [], "charts": []}}
