"""受限 Pandas 统计分析工具（白名单操作，不执行任意代码）。"""
import json
import logging

import pandas as pd
from langchain_core.tools import tool

from app.data.loader import load_dataset
from app.tools.convert import df_to_table
from app.tools.models import AnalysisRequest

logger = logging.getLogger(__name__)

_MAX_GROUP_SERIES = 8  # grouped_trend 宽表最多列数
# pandas 3.x: 'M'/'Y' 已弃用，映射为 'ME'/'YE'（周期期末）
_FREQ_MAP = {"D": "D", "W": "W", "M": "ME", "Y": "YE"}


def _apply_where(df: pd.DataFrame, req: AnalysisRequest) -> pd.DataFrame:
    if req.where_col and req.where_value is not None:
        df = df[df[req.where_col].astype(str) == str(req.where_value)]
    return df


def _op_mask(col: pd.Series, op: str, v) -> pd.Series:
    if op == "==":
        return col == v
    if op == "!=":
        return col != v
    if op == ">":
        return col > v
    if op == ">=":
        return col >= v
    if op == "<":
        return col < v
    if op == "<=":
        return col <= v
    raise ValueError(f"不支持的操作符: {op}")


def execute_analysis(df: pd.DataFrame, req: AnalysisRequest) -> dict:
    """执行白名单分析操作，返回 TableResult 字典。"""
    df = _apply_where(df, req)
    ops = req.operation
    title = f"[{req.dataset}] "

    if ops == "head":
        return df_to_table(df, title + "数据预览", limit=req.limit)

    if ops == "describe":
        sub = df.select_dtypes(include="number").describe()
        return df_to_table(sub, title + "数值列统计摘要", index_name="统计量")

    if ops == "groupby_agg":
        if not req.group_by or not req.value_col:
            raise ValueError("groupby_agg 需要 group_by 与 value_col 参数")
        if req.value_col2:
            # 双聚合：同时算两个指标列（如违约人数 + 违约率）
            gb_col = str(req.group_by)
            col1_name = f"{req.value_col}_{req.agg}"
            col2_name = f"{req.value_col2}_{req.agg2}"
            # 若聚合列名与分组列撞名则加前缀，避免 reset_index 冲突
            if gb_col in (col1_name, col2_name):
                col1_name = f"{gb_col}_{col1_name}" if col1_name == gb_col else col1_name
                col2_name = f"{gb_col}_{col2_name}" if col2_name == gb_col else col2_name
            sub = df.groupby(gb_col).agg(
                **{col1_name: (req.value_col, req.agg), col2_name: (req.value_col2, req.agg2)}
            ).reset_index().sort_values(col1_name, ascending=req.ascending).head(req.limit)
            return df_to_table(
                sub, f"{title}{gb_col} 按 {req.value_col}({req.agg}) 与 {req.value_col2}({req.agg2})",
                chart_type="bar", chart_cols=[col1_name], y2_cols=[col2_name], limit=req.limit
            )
        # 数值列名可能等于分组列名（如按 LIMIT_BAL 分组又求 LIMIT_BAL 均值的均值），先重命名避免 reset_index 冲突
        gb_col = str(req.group_by)
        val_name = str(req.value_col)
        if val_name == gb_col:
            val_name = f"{val_name}_{req.agg}"
        sub = (
            df.groupby(gb_col)[req.value_col]
            .agg(req.agg)
            .rename(val_name)
            .reset_index()
            .sort_values(val_name, ascending=req.ascending)
            .head(req.limit)
        )
        return df_to_table(
            sub, f"{title}{gb_col} 按 {req.value_col} 聚合({req.agg})", chart_type="bar", limit=req.limit
        )

    if ops == "rate_agg":
        # 按分组计算 人数(count) + 比率(rate)。专门用于"某标签列（如 DEFAULT）分组下的比率"，
        # 自动同时输出 count 与 rate，并配双 Y 轴（柱=人数，线=比率）。
        if not req.group_by or not req.value_col:
            raise ValueError("rate_agg 需要 group_by 与 value_col（0/1 标签列，如 DEFAULT）参数")
        gb_col = str(req.group_by)
        label_col = str(req.value_col)
        count_name = f"{label_col}_count"
        rate_name = f"{label_col}_rate"
        # 数值分组列（如 AGE）按 bin_size 分箱，避免切成几百个分组
        if req.bin_size and pd.api.types.is_numeric_dtype(df[gb_col]):
            bucket = (df[gb_col] // req.bin_size * req.bin_size).astype(int).astype(str) + "+"
            group_series = bucket
            gb_label = f"{gb_col}(每{req.bin_size}岁)"
        else:
            group_series = df[gb_col]
            gb_label = gb_col
        tmp = df.copy()
        tmp["_g"] = group_series
        sub = (
            tmp.groupby("_g")
            .agg(**{count_name: (label_col, "count"), rate_name: (label_col, "mean")})
            .reset_index()
            .rename(columns={"_g": gb_label})
            .sort_values(count_name, ascending=req.ascending)
            .head(req.limit)
        )
        return df_to_table(
            sub, f"{title}{gb_label} 违约情况（人数 + {label_col}比率）",
            chart_type="bar", chart_cols=[count_name], y2_cols=[rate_name], limit=req.limit
        )

    if ops == "time_trend":
        if not req.date_col or not req.value_col:
            raise ValueError("time_trend 需要 date_col 与 value_col 参数")
        d = df.copy()
        d[req.date_col] = pd.to_datetime(d[req.date_col], errors="coerce")
        d = d.dropna(subset=[req.date_col])
        s = d.set_index(req.date_col)[req.value_col].resample(_FREQ_MAP[req.freq]).agg(req.agg)
        s = s.to_frame(name=req.value_col)
        s.index = s.index.strftime("%Y-%m-%d")
        return df_to_table(
            s, f"{title}{req.value_col} 时间趋势（{req.freq}）", index_name=req.date_col, chart_type="line", limit=req.limit
        )

    if ops == "grouped_trend":
        if not req.date_col or not req.value_col or not req.group_by:
            raise ValueError("grouped_trend 需要 date_col、value_col 与 group_by 参数")
        d = df.copy()
        d[req.date_col] = pd.to_datetime(d[req.date_col], errors="coerce")
        d = d.dropna(subset=[req.date_col])
        freq_key = _FREQ_MAP[req.freq]
        try:
            pivot = d.pivot_table(
                index=pd.Grouper(key=req.date_col, freq=freq_key),
                columns=req.group_by,
                values=req.value_col,
                aggfunc=req.agg,
                dropna=False,
            )
        except (ValueError, TypeError) as e:  # 分组列类型异常时自动降级为 time_trend 单序列
            logger.warning("grouped_trend pivot 失败(%s)，降级为 time_trend", e)
            s = d.set_index(req.date_col)[req.value_col].resample(freq_key).agg(req.agg).to_frame(name=req.value_col)
            s.index = s.index.strftime("%Y-%m-%d")
            return df_to_table(
                s, f"{title}{req.value_col} 时间趋势（{req.freq}）", index_name=req.date_col, chart_type="line", limit=req.limit
            )
        if pivot.empty:
            return df_to_table(pivot, title + "无数据", limit=req.limit)
        # 按总量保留最多 _MAX_GROUP_SERIES 个分组，避免图表过宽
        totals = pivot.sum(skipna=True).sort_values(ascending=False)
        pivot = pivot[totals.index[: _MAX_GROUP_SERIES]]
        pivot.index = pivot.index.strftime("%Y-%m-%d")
        return df_to_table(
            pivot,
            f"{title}{req.value_col} 按 {req.group_by} 对比（{req.freq}）",
            index_name=req.date_col,
            chart_type="line",
            limit=req.limit,
        )

    if ops == "top_n":
        if not req.value_col:
            raise ValueError("top_n 需要 value_col 参数")
        sub = df.sort_values(req.value_col, ascending=req.ascending).head(req.top)
        return df_to_table(sub, f"{title}按 {req.value_col} 排序前 {req.top} 行", limit=req.top)

    if ops == "filter_rows":
        if not req.column or req.value is None:
            raise ValueError("filter_rows 需要 column 与 value 参数")
        col = df[req.column]
        if req.op == "contains":
            # 子串匹配：统一转为字符串，不做数值/日期比较
            mask = col.astype(str).str.contains(str(req.value), case=False, na=False)
        elif pd.api.types.is_datetime64_any_dtype(col):
            mask = _op_mask(col, req.op, pd.to_datetime(req.value))
        else:
            try:
                v = float(req.value)
                mask = _op_mask(pd.to_numeric(col, errors="coerce"), req.op, v)
            except ValueError:
                mask = _op_mask(col.astype(str), req.op, str(req.value))
        sub = df[mask].head(req.limit)
        return df_to_table(sub, f"{title}筛选 {req.column}{req.op}{req.value}", limit=req.limit)

    if ops == "correlation":
        cols = req.columns or [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if len(cols) < 2:
            raise ValueError("correlation 需要至少两个数值列")
        sub = df[cols].corr().round(4)
        return df_to_table(sub, title + "数值列相关性矩阵", index_name="变量")

    raise ValueError(f"未知操作: {ops}")


@tool(args_schema=AnalysisRequest)
def analyze_data(
    dataset: str,
    operation: str,
    value_col: str | None = None,
    group_by: str | None = None,
    bin_size: int | None = None,
    date_col: str | None = None,
    agg: str = "sum",
    value_col2: str | None = None,
    agg2: str = "mean",
    freq: str = "M",
    top: int = 10,
    ascending: bool = False,
    column: str | None = None,
    op: str = "==",
    value: str | None = None,
    columns: list[str] | None = None,
    where_col: str | None = None,
    where_value: str | None = None,
    limit: int = 30,
) -> str:
    """对指定数据集执行受限统计分析，返回一个 JSON 表格（TableResult 字典）。

    - dataset 必填，取 list_datasets 中的 name；
    - 常见组合：
      * groupby_agg + group_by + value_col：分组汇总（柱状图）
      * rate_agg + group_by + value_col：按分组计算标签列（如 DEFAULT）的 人数(count)+比率(rate)，
        自动返回两列并配双 Y 轴（柱=人数、线=比率）。查询"各XX的违约率/占比"时优选用它；
        分组列为连续数值（如实名 AGE）时应传 bin_size（如 10）将年龄切成区间。
      * groupby_agg + group_by + value_col + agg + value_col2 + agg2：双指标分组汇总
        （如 value_col=DEFAULT agg=count 得违约人数, value_col2=DEFAULT agg2=mean 得违约率,
        返回的表格自动设置 chart_cols 和 y2_cols，渲染为左轴柱状图+右轴折线双 Y 轴图）
      * time_trend + date_col + value_col + freq：单序列时间趋势（折线图）
      * grouped_trend + group_by + date_col + value_col：多组时间对比（多折线）
      * top_n + value_col：按数值排序取前 N 行
      * filter_rows + column + op + value：条件过滤
      * describe：数值统计摘要；correlation + columns：相关性矩阵
    """
    try:
        req = AnalysisRequest(
            dataset=dataset,
            operation=operation,
            value_col=value_col,
            group_by=group_by,
            bin_size=bin_size,
            date_col=date_col,
            agg=agg,
            freq=freq,
            top=top,
            ascending=ascending,
            column=column,
            op=op,
            value=value,
            columns=columns,
            where_col=where_col,
            where_value=where_value,
            limit=limit,
        )
        df = load_dataset(req.dataset)
        result = execute_analysis(df, req)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        logger.exception("analyze_data 执行失败")
        return json.dumps(
            {
                "error": f"分析失败: {e}",
                "suggestion": "请检查参数是否与数据集字段一致，可先调用 list_datasets 查看字段。",
            },
            ensure_ascii=False,
        )
