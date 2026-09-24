"""
电商月度销售分析报告
====================
数据源: app/data/raw/ecommerce_retail.csv (UCI Online Retail 数据集, ~54万行)

输出物:
  1. 月销售额折线图 (含环比双轴)        -> reports/monthly_sales_line.html
  2. 电商转化漏斗图 (访问→加购→结算→下单) -> reports/conversion_funnel.html
  3. 月度指标 Pivot Table (CSV/Excel)    -> reports/monthly_pivot.csv
  4. 完整月报文字摘要                     -> 控制台 + reports/monthly_report.txt

指标定义:
  - 月销售额 Revenue   = Σ(Quantity * UnitPrice)   (已剔除退货/取消单)
  - 订单数 Orders       = InvoiceNo 去重计数
  - 客单价 AOV          = Revenue / Orders
  - 转化率 CVR          = Orders / Visits           (Visits 按行业基准 2.5% 反推模拟)
  - ROAS               = Revenue / AdSpend          (AdSpend 按收入 10% 模拟)
  - 环比 MoM           = (本月-上月)/上月
  - 趋势 Trend          = 月销售额线性回归斜率
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ----------------------------------------------------------------------
# 0. 路径与输出目录
# ----------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "app" / "data" / "raw" / "ecommerce_retail.csv"
REPORT_DIR = PROJECT_ROOT / "reports"
REPORT_DIR.mkdir(exist_ok=True)


# ----------------------------------------------------------------------
# 1. 读取与清洗
# ----------------------------------------------------------------------
def load_and_clean(path: Path) -> pd.DataFrame:
    """读取 CSV 并做基础清洗 (退货/取消单、非正值、缺失客户)。"""
    df = pd.read_csv(path, parse_dates=["InvoiceDate"])

    # 1.1 去除退货/取消订单 (InvoiceNo 以 'C' 开头)
    df = df[~df["InvoiceNo"].astype(str).str.startswith("C")].copy()

    # 1.2 过滤 Quantity<=0 或 UnitPrice<=0 的异常行
    df = df[(df["Quantity"] > 0) & (df["UnitPrice"] > 0)]

    # 1.3 去除 CustomerID 缺失
    df = df.dropna(subset=["CustomerID"])

    # 1.4 安全起见: Revenue 若不存在则补算
    if "Revenue" not in df.columns:
        df["Revenue"] = df["Quantity"] * df["UnitPrice"]
    else:
        df["Revenue"] = df["Quantity"] * df["UnitPrice"]

    # 1.5 月份字段
    df["YearMonth"] = df["InvoiceDate"].dt.to_period("M").astype(str)

    print(f"[清洗后] 行数: {len(df):,}  月份范围: {df['YearMonth'].min()} ~ {df['YearMonth'].max()}")
    return df


# ----------------------------------------------------------------------
# 2. 月度聚合
# ----------------------------------------------------------------------
def monthly_aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """按月聚合核心指标, 并计算 AOV / 环比 / 模拟 Visits/AdSpend/CVR/ROAS。"""
    g = df.groupby("YearMonth").agg(
        Revenue=("Revenue", "sum"),
        Orders=("InvoiceNo", "nunique"),
        Customers=("CustomerID", "nunique"),
        Items=("Quantity", "sum"),
    ).reset_index().sort_values("YearMonth")

    # 客单价 AOV
    g["AOV"] = (g["Revenue"] / g["Orders"]).round(2)

    # 环比 MoM (百分比)
    g["MoM_%"] = (g["Revenue"].pct_change() * 100).round(2)

    # —— 模拟外部指标 (教学演示, 数据集中无流量/广告费) ——
    np.random.seed(42)
    # 行业基准转化率 2.5% 上下浮动 → 反推 Visits = Orders / CVR
    cvr_sim = np.random.uniform(0.020, 0.030, size=len(g))
    g["Visits"] = (g["Orders"] / cvr_sim).round().astype(int)
    g["CVR_%"] = (g["Orders"] / g["Visits"] * 100).round(2)

    # 假设广告费 = 收入的 10% ± 噪声 → ROAS = Revenue / AdSpend
    ad_spend_ratio = np.random.uniform(0.08, 0.12, size=len(g))
    g["AdSpend"] = (g["Revenue"] * ad_spend_ratio).round(2)
    g["ROAS"] = (g["Revenue"] / g["AdSpend"]).round(2)

    # 趋势: 线性回归斜率 (整体)
    x = np.arange(len(g))
    slope = np.polyfit(x, g["Revenue"].values, 1)[0]
    g.attrs["trend_slope"] = slope
    g.attrs["trend_dir"] = "上升 ↑" if slope > 0 else "下降 ↓"
    return g


# ----------------------------------------------------------------------
# 3. 折线图: 月销售额 + 环比双轴
# ----------------------------------------------------------------------
def plot_sales_line(monthly: pd.DataFrame) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=monthly["YearMonth"], y=monthly["Revenue"],
        name="月销售额", mode="lines+markers",
        line=dict(color="#1f77b4", width=3),
        hovertemplate="月份: %{x}<br>销售额: £%{y:,.0f}<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=monthly["YearMonth"], y=monthly["MoM_%"],
        name="环比 %", marker_color="#ff7f0e",
        hovertemplate="月份: %{x}<br>环比: %{y:.2f}%<extra></extra>",
    ), secondary_y=True)
    fig.update_layout(
        title="月销售额趋势 + 环比增长率 (双轴)",
        hovermode="x unified", template="plotly_white",
        legend=dict(orientation="h", y=1.12),
        height=480,
    )
    fig.update_yaxes(title_text="销售额 (£)", secondary_y=False)
    fig.update_yaxes(title_text="环比增长率 (%)", secondary_y=True)
    return fig


# ----------------------------------------------------------------------
# 4. 漏斗图: 访问 → 加购 → 结算 → 下单
# ----------------------------------------------------------------------
def plot_funnel(monthly: pd.DataFrame) -> go.Figure:
    """按经典电商漏斗模拟四阶段, 比例取行业经验值。"""
    total_visits = int(monthly["Visits"].sum())
    cart = int(total_visits * 0.30)     # 加购率 30%
    checkout = int(cart * 0.50)         # 结算率 50%
    purchase = int(monthly["Orders"].sum())

    stages = ["访问 Visits", "加购 Cart", "结算 Checkout", "下单 Purchase"]
    values = [total_visits, cart, checkout, purchase]
    fig = go.Figure(go.Funnel(
        y=stages, x=values,
        textinfo="value+percent initial+percent previous",
        marker=dict(color=["#6366f1", "#8b5cf6", "#ec4899", "#f43f5e"]),
        connector=dict(line=dict(color="#cbd5e1", width=2)),
    ))
    fig.update_layout(
        title="电商转化漏斗 (访问 → 加购 → 结算 → 下单)",
        template="plotly_white", height=420,
    )
    return fig


# ----------------------------------------------------------------------
# 5. Pivot Table 月报
# ----------------------------------------------------------------------
def build_pivot(monthly: pd.DataFrame) -> pd.DataFrame:
    """长表转宽表: 行=月份, 列=各指标 (用于月报阅读)。"""
    cols = ["Revenue", "Orders", "Customers", "Items", "AOV",
            "MoM_%", "CVR_%", "ROAS", "Visits", "AdSpend"]
    pretty = monthly[["YearMonth"] + cols].rename(columns={
        "YearMonth": "月份",
        "Revenue": "销售额(£)",
        "Orders": "订单数",
        "Customers": "客户数",
        "Items": "商品件数",
        "AOV": "客单价(£)",
        "MoM_%": "环比(%)",
        "CVR_%": "转化率(%)",
        "ROAS": "ROAS",
        "Visits": "访问量",
        "AdSpend": "广告费(£)",
    })
    return pretty


# ----------------------------------------------------------------------
# 6. 文字月报
# ----------------------------------------------------------------------
def build_report_text(monthly: pd.DataFrame, pivot: pd.DataFrame) -> str:
    last = monthly.iloc[-1]
    prev = monthly.iloc[-2] if len(monthly) > 1 else last
    slope = monthly.attrs["trend_slope"]
    direction = monthly.attrs["trend_dir"]
    peak = monthly.loc[monthly["Revenue"].idxmax()]

    lines = []
    lines.append("=" * 60)
    lines.append("电商月度销售分析报告")
    lines.append("=" * 60)
    lines.append(f"数据期: {monthly['YearMonth'].min()} ~ {monthly['YearMonth'].max()}")
    lines.append(f"数据集: {DATA_PATH.name}")
    lines.append("")
    lines.append("【整体趋势】")
    lines.append(f"  月均销售额斜率: £{slope:,.0f}/月  → 整体{direction}")
    lines.append(f"  销售额峰值月: {peak['YearMonth']}  £{peak['Revenue']:,.0f}")
    lines.append("")
    lines.append("【最新月份快照】")
    lines.append(f"  月份: {last['YearMonth']}")
    lines.append(f"  销售额: £{last['Revenue']:,.0f}  (环比 {last['MoM_%']:+.2f}%)")
    lines.append(f"  订单数: {last['Orders']:,}  客户数: {last['Customers']:,}")
    lines.append(f"  客单价 AOV: £{last['AOV']:.2f}")
    lines.append(f"  转化率 CVR: {last['CVR_%']:.2f}%  (访问 {last['Visits']:,})")
    lines.append(f"  ROAS: {last['ROAS']:.2f}  (广告费 £{last['AdSpend']:,.0f})")
    lines.append("")
    lines.append("【环比同比变化 Top 3 月份】")
    top_mom = monthly.nlargest(3, "MoM_%")[["YearMonth", "MoM_%", "Revenue"]]
    for _, r in top_mom.iterrows():
        lines.append(f"  {r['YearMonth']}: 环比 +{r['MoM_%']:.2f}%  (销售额 £{r['Revenue']:,.0f})")
    lines.append("")
    lines.append("【完整 Pivot Table (CSV 已保存)】")
    lines.append(pivot.to_string(index=False))
    lines.append("=" * 60)
    return "\n".join(lines)


# ----------------------------------------------------------------------
# 7. 主流程
# ----------------------------------------------------------------------
def main() -> None:
    print(">>> 步骤 1: 加载与清洗")
    df = load_and_clean(DATA_PATH)

    print(">>> 步骤 2: 月度聚合 + 指标计算")
    monthly = monthly_aggregate(df)

    print(">>> 步骤 3: 绘制折线图")
    fig_line = plot_sales_line(monthly)
    fig_line.write_html(REPORT_DIR / "monthly_sales_line.html", include_plotlyjs="cdn")

    print(">>> 步骤 4: 绘制漏斗图")
    fig_funnel = plot_funnel(monthly)
    fig_funnel.write_html(REPORT_DIR / "conversion_funnel.html", include_plotlyjs="cdn")

    print(">>> 步骤 5: 生成 Pivot Table 月报")
    pivot = build_pivot(monthly)
    pivot.to_csv(REPORT_DIR / "monthly_pivot.csv", index=False, encoding="utf-8-sig")

    print(">>> 步骤 6: 生成文字月报")
    report = build_report_text(monthly, pivot)
    (REPORT_DIR / "monthly_report.txt").write_text(report, encoding="utf-8")
    print()
    print(report)


if __name__ == "__main__":
    main()
