"""结构化模型：分析请求 / 表格结果 / 交付物。"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.data.sources import dataset_names

DatasetName = Literal[*dataset_names()]  # type: ignore[misc]

OpType = Literal[
    "head",
    "describe",
    "groupby_agg",
    "rate_agg",
    "time_trend",
    "grouped_trend",
    "top_n",
    "filter_rows",
    "correlation",
]


class AnalysisRequest(BaseModel):
    """一次受限统计分析请求（白名单操作）。"""

    dataset: DatasetName = Field(description="要分析的数据集名称（来自 list_datasets 返回的 name）")
    operation: OpType = Field(description="分析操作类型")
    value_col: Optional[str] = Field(default=None, description="数值列，用于聚合/趋势/排序")
    group_by: Optional[str] = Field(default=None, description="分组列，groupby_agg/rate_agg/grouped_trend 使用")
    bin_size: Optional[int] = Field(default=None, description="rate_agg 对数值分组列（如 AGE）的分箱宽度；按连续数值分组时用，用于把年龄等切成区间")
    date_col: Optional[str] = Field(default=None, description="日期列，time_trend/grouped_trend 使用")
    agg: Literal["sum", "mean", "count", "min", "max"] = Field(default="sum", description="聚合方式")
    value_col2: Optional[str] = Field(default=None, description="可选第二聚合列。设置后 groupby_agg 同时返回两个聚合结果列（如 value_col=DEFAULT agg=count 得违约人数，value_col2=DEFAULT agg2=mean 得违约率）")
    agg2: Literal["sum", "mean", "count", "min", "max"] = Field(default="mean", description="第二聚合方式")
    freq: Literal["D", "W", "M", "Y"] = Field(default="M", description="时间重采样频率：D日/W周/M月/Y年")
    top: int = Field(default=10, description="top_n 返回条数")
    ascending: bool = Field(default=False, description="排序方向（False 降序）")
    column: Optional[str] = Field(default=None, description="filter_rows 过滤列")
    op: Literal["==", "!=", ">", ">=", "<", "<=", "contains"] = Field(
        default="==", description="filter_rows 比较符"
    )
    value: Optional[str] = Field(default=None, description="filter_rows 过滤值")
    columns: Optional[list[str]] = Field(default=None, description="correlation 参与计算的数值列")
    where_col: Optional[str] = Field(default=None, description="可选：先按此列过滤（等值）")
    where_value: Optional[str] = Field(default=None, description="可选：where_col 对应的过滤值")
    limit: int = Field(default=30, description="结果最大行数")


class TableResult(BaseModel):
    """统一表格交付物。index_name 非空时每行首列为索引值。"""

    title: str
    columns: list[str]
    index_name: Optional[str] = None
    rows: list[list]
    chart_type: Literal["line", "bar", "pie", "none"] = "none"
    chart_cols: Optional[list[str]] = Field(
        default=None,
        description="指定左 Y 轴绘制的数值列。不指定时默认绘制所有数值列。",
    )
    y2_cols: Optional[list[str]] = Field(
        default=None,
        description="指定右 Y 轴绘制的数值列（用于量纲不同的指标，如违约率叠加在违约人数柱状图上）。设置后这些列用右侧 Y 轴、折线图渲染，chart_cols 的列用左侧 Y 轴、柱状图渲染。",
    )
    note: str = ""


class DeliverRequest(BaseModel):
    """Agent 最终交付物。"""

    summary: str = Field(description="中文分析结论摘要")
    tables: list[TableResult] = Field(
        description="所有结果表格，须与 analyze_data 返回的表格一致，原样保留，不得增删行或改动数值"
    )
