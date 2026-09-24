"""数值清理与 DataFrame → 结构化表格 转换工具。"""
import math
from typing import Any

import pandas as pd


def clean_value(v: Any) -> Any:
    """将 numpy / pandas 标量转为可 JSON 序列化的 Python 值。"""
    if v is None:
        return None
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (pd.Timedelta,)):
        return str(v)
    if hasattr(v, "item"):  # numpy 标量
        return v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def df_to_jsonable(df: pd.DataFrame, limit: int = 200) -> list[dict]:
    return [{k: clean_value(v) for k, v in r.items()} for r in df.head(limit).to_dict(orient="records")]


def df_to_table(
    df: pd.DataFrame,
    title: str,
    index_name: str | None = None,
    chart_type: str = "none",
    chart_cols: list[str] | None = None,
    y2_cols: list[str] | None = None,
    limit: int = 50,
) -> dict:
    """DataFrame → TableResult 字典。传入 index_name 时其列作为首列（索引）。

    调用约定：若需要索引列进入表格，请先把该列设为 DataFrame 索引并传入 index_name。
    chart_cols: 左 Y 轴绘制的列名列表。
    y2_cols: 右 Y 轴绘制的列名列表（量纲不同的指标，如违约率叠加在人数柱状图上）。
    """
    df = df.head(limit).copy()
    if index_name is not None:
        df.index.name = index_name
        df = df.reset_index()
    columns = [str(c) for c in df.columns]
    rows = [[clean_value(v) for v in r] for r in df.itertuples(index=False, name=None)]
    result = {
        "title": title,
        "columns": columns,
        "index_name": index_name,
        "rows": rows,
        "chart_type": chart_type,
    }
    if chart_cols:
        result["chart_cols"] = chart_cols
    if y2_cols:
        result["y2_cols"] = y2_cols
    return result
