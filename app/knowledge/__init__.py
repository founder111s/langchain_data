"""领域知识库：数据集的业务口径、字段含义、分析建议与常见问答。

RAG 的"知识"来源。每个条目是一个带标签的文本块，供 query_knowledge 检索。
不以字段名映射为主，而是补充"该列怎么解读""该数据集适合做什么分析"等 LLM 记忆之外的领域知识。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnowledgeDoc:
    title: str
    domain: str  # 关联的数据集 name 或领域关键词
    content: str
    keywords: tuple[str, ...] = ()  # 确定性检索的关键词，用于 embedding 不可用时的兜底


# 业务口径/领域知识条目（可随项目扩充）
KNOWLEDGE_DOCS: list[KnowledgeDoc] = [
    KnowledgeDoc(
        title="信用卡违约数据集字段口径",
        domain="credit",
        keywords=("credit", "违约", "DEFAULT", "信用卡", "银行风控", "逾期"),
        content=(
            "credit 数据集（UCI Default of Credit Card Clients）是台湾信用卡客户违约数据，共约 3 万条。\n"
            "关键字段口径：LIMIT_BAL=信用额度（新台币）；SEX=性别（1男 2女）；"
            "EDUCATION=教育程度（1研究生 2大学 3高中 4其他）；MARRIAGE=婚姻（1已婚 2单身 3其他）；"
            "PAY_0~PAY_6=过去1-6个月还款状态（-1准时 0未消费 1-9延迟月数）；"
            "BILL_AMT1~6=过去1-6个月账单金额；PAY_AMT1~6=同期还款金额；DEFAULT=下月是否违约（1是 0否）。"
            "违约率=DEFAULT 的均值。分析风控时常用 rate_agg 同时看人数与违约率。"
        ),
    ),
    KnowledgeDoc(
        title="信用卡风控的分析价值",
        domain="credit",
        keywords=("credit", "风控", "评分卡", "违约率", "银行"),
        content=(
            "信用卡违约预测是银行风控的核心场景，可延伸出评分卡模型。常用分析维度：\n"
            "- 人口属性（性别/教育/婚姻/年龄）与违约率的关系；\n"
            "- 还款行为（PAY_* 延期月数）与违约的正相关性；\n"
            "- 信用额度区间与风险分布。\n"
            "面试时可强调：本项目用 rate_agg 直接产出人数+违约率双指标，并支持按年龄分箱（bin_size）。"
        ),
    ),
    KnowledgeDoc(
        title="电商零售数据集字段口径",
        domain="ecommerce",
        keywords=("ecommerce", "电商", "销售额", "Revenue", "零售", "Country"),
        content=(
            "ecommerce 数据集（UCI Online Retail）是跨境电商订单，约 54 万行，时间 2010-12 至 2011-12。\n"
            "关键字段：InvoiceNo=发票号，StockCode=商品编码，Description=商品描述，Quantity=数量，"
            "InvoiceDate=发票日期，UnitPrice=单价，CustomerID=客户ID，Country=国家，Revenue=销售额（=数量×单价）。\n"
            "分析常用：按 Country 分组汇总销售额；按 InvoiceDate 看月度/每日销售趋势。"
        ),
    ),
    KnowledgeDoc(
        title="金融股票数据集字段口径",
        domain="finance",
        keywords=("finance", "金融", "股票", "Ticker", "收盘价", "AAPL", "行情"),
        content=(
            "finance 数据集是 AAPL/MSFT/GOOG/TSLA 近一年日线（前复权）。\n"
            "字段：Date=交易日，Ticker=股票代码，Open/High/Low/Close=开/高/低/收盘价，Volume=成交量。\n"
            "分析常用：单只股票 time_trend + where_col=Ticker；多只股票 grouped_trend 或 groupby_agg 对比收盘价。"
        ),
    ),
    KnowledgeDoc(
        title="气候气象数据集字段口径",
        domain="climate",
        keywords=("climate", "气候", "气象", "气温", "北京", "降水", "City"),
        content=(
            "climate 数据集是北京/上海/纽约/伦敦近两年逐日气象。\n"
            "字段：Date=日期，City=城市，tmax=最高气温（℃），tmin=最低气温（℃），precipitation=降水量（mm）。\n"
            "分析常用：按 City 对比平均温度；按 Date 看季节趋势。"
        ),
    ),
    KnowledgeDoc(
        title="公共卫生 COVID-19 数据集字段口径",
        domain="health",
        keywords=("health", "健康", "疫情", "COVID", "确诊", "新增", "死亡"),
        content=(
            "health 数据集是 COVID-19 全球公开数据（部分国家，2020 至今）。\n"
            "字段：date=日期，location=国家/地区，total_cases=累计确诊，new_cases=新增确诊，"
            "total_deaths=累计死亡，new_deaths=新增死亡。\n"
            "分析常用：某国 time_trend（where_col=location）；多国 grouped_trend 对比趋势；groupby_agg 汇总累计值。"
        ),
    ),
    KnowledgeDoc(
        title="数据分析 Agent 使用说明",
        domain="general",
        keywords=("agent", "用法", "数据集", "list_datasets", "工具", "帮助"),
        content=(
            "数据分析 Agent 的工作方式：\n"
            "1. 先用 list_datasets 查看可用数据集及字段；\n"
            "2. 用 analyze_data 执行白名单分析，支持 groupby_agg / rate_agg / time_trend / grouped_trend / top_n / filter_rows / correlation；\n"
            "3. 违约率类问句用 rate_agg；双指标用 chart_cols/y2_cols 双 Y 轴；\n"
            "4. 最后用 deliver 交付表格+summary。"
        ),
    ),
]


def build_contents_by_domain() -> dict[str, str]:
    """将每个数据集（或通用域）的知识合并为一段文本，供向量索引。"""
    merged: dict[str, list[str]] = {}
    for doc in KNOWLEDGE_DOCS:
        merged.setdefault(doc.domain, []).append(f"[{doc.title}]\n{doc.content}")
    return {k: "\n\n".join(v) for k, v in merged.items()}


def doc_titles() -> list[str]:
    return [d.title for d in KNOWLEDGE_DOCS]


def _normalize(s: str) -> str:
    return s.strip().lower()