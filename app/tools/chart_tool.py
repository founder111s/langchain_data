"""表格 → Plotly 图表规格生成器。"""
import logging
from typing import Any

import plotly.graph_objects as go

from app.tools.convert import clean_value
from app.tools.models import TableResult

logger = logging.getLogger(__name__)


def _extract_series(rows: list[list], cols: list[str], col_names: list[str]) -> list[list]:
    """从 rows 中提取指定列的数据，返回 series 列表。"""
    col_idx_map = {c: i for i, c in enumerate(cols)}
    series = []
    for cn in col_names:
        ci = col_idx_map.get(cn)
        if ci is None:
            continue
        series.append([clean_value(r[ci]) for r in rows])
    return series


def table_to_plotly(table: TableResult) -> dict:
    """将 TableResult 转为 Plotly 图，返回 to_plotly_json() 字典。

    - line: 单序列或多序列折线
    - bar: 柱状图（多序列时分组柱）
    - pie: 饼图（首列类别、次列数值）
    - y2_cols 指定时：左 Y 轴画 chart_cols（柱状图），右 Y 轴画 y2_cols（折线图叠加）
    """
    rows = table.rows
    cols = table.columns
    has_index = bool(table.index_name)
    chart = table.chart_type
    fig = go.Figure()

    if not rows:
        fig.update_layout(title=table.title, xaxis_title=cols[0] if cols else "")
        return fig.to_plotly_json()

    if has_index:
        x = [clean_value(r[0]) for r in rows]
        all_y_cols = cols[1:]
    else:
        x = list(range(len(rows)))
        all_y_cols = cols

    # 左轴列 = chart_cols（指定时）或全部数值列
    left_cols = table.chart_cols or all_y_cols
    # 右轴列 = y2_cols（量纲不同的列，用右轴折线叠加）
    right_cols = table.y2_cols or []

    # 从 left_cols 中排除已分配到右轴的列
    left_cols = [c for c in left_cols if c not in right_cols]

    left_series = _extract_series(rows, cols, left_cols)
    right_series = _extract_series(rows, cols, right_cols)

    # pie 图不支持双轴，走原逻辑
    if chart == "pie":
        labels = x if has_index else [clean_value(r[0]) for r in rows]
        values = left_series[0] if left_series else []
        fig.add_trace(go.Pie(labels=labels, values=values, name=table.title))
    elif chart == "bar":
        # 左轴：柱状图
        for name, ys in zip(left_cols, left_series):
            fig.add_trace(go.Bar(x=x, y=ys, name=name))
        fig.update_layout(barmode="group")
        # 右轴：折线叠加（如违约率）
        for name, ys in zip(right_cols, right_series):
            fig.add_trace(go.Scatter(
                x=x, y=ys, mode="lines+markers", name=name,
                yaxis="y2", line=dict(width=2),
            ))
    elif chart == "line":
        # 左轴折线
        for name, ys in zip(left_cols, left_series):
            fig.add_trace(go.Scatter(x=x, y=ys, mode="lines+markers", name=name))
        # 右轴折线
        for name, ys in zip(right_cols, right_series):
            fig.add_trace(go.Scatter(
                x=x, y=ys, mode="lines+markers", name=name,
                yaxis="y2", line=dict(width=2, dash="dot"),
            ))
    else:
        fig.add_trace(go.Scatter(x=x, y=left_series[0] if left_series else [],
                                 mode="markers", name=left_cols[0] if left_cols else ""))

    layout_dict = dict(
        title=table.title,
        xaxis_title=table.index_name or (cols[0] if cols else ""),
        yaxis_title="、".join(left_cols[:3]) if left_cols else "",
        margin=dict(l=50, r=50, t=60, b=40),
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )
    # 有右轴时添加 y2 配置
    if right_cols:
        layout_dict["yaxis2"] = dict(
            overlaying="y",
            side="right",
            title="、".join(right_cols[:3]),
            showgrid=False,
        )
    fig.update_layout(**layout_dict)
    return fig.to_plotly_json()
