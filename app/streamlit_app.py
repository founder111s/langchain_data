"""Streamlit 网站：对话式数据分析 Agent（表格 + 图表交付）。"""
import logging
import sys
from pathlib import Path

# 确保项目根目录可导入 app 包（Streamlit 启动时 CWD 不在 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.agent.graph import run_analysis
from app.config import settings, setup_logging
from app.data.loader import load_all_meta
from app.llm import configure_langsmith, get_llm

setup_logging()
configure_langsmith()
logger = logging.getLogger(__name__)

st.set_page_config(page_title="LangChain 数据分析 Agent", layout="wide")

EXAMPLES = [
    "各教育程度违约率对比（银行风控）",
    "查询各年龄的违约率（银行风控）",
    "不同信用额度区间的违约人数（银行风控）",
    "各年龄组违约率对比（银行风控）",
    "男女客户违约率对比（银行风控）",
    "各国家销售额对比（电商）",
    "按国家对比销售额，并列出前3名（电商）",
    "电商每月销售额趋势",
    "AAPL 收盘价走势（金融）",
    "各股票平均收盘价对比（金融）",
    "对比中国和英国的新增确诊趋势（健康）",
    "各城市月平均最高温对比（气候）",
    "北京近一年平均气温趋势（气候）",
    "各国每月新增确诊对比（健康）",
    "各股票收盘价相关性（金融）",
]


@st.cache_resource
def _get_llm():
    return get_llm()


def table_to_df(t: dict) -> pd.DataFrame:
    df = pd.DataFrame(t["rows"], columns=t["columns"])
    if t.get("index_name") in df.columns:
        df = df.set_index(t["index_name"])
    # 统一 object 列类型（填充 NaN），避免 Streamlit 混入 float 导致 Arrow 序列化失败
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].where(df[c].notna(), None)
    return df


def render_result(rendered: dict, key_prefix: str = "") -> None:
    """渲染一次分析结果。key_prefix 用于在多轮对话中保证 Streamlit 元素 key 全局唯一。"""
    st.markdown(rendered.get("summary", ""))
    for i, t in enumerate(rendered.get("tables", [])):
        st.dataframe(table_to_df(t), use_container_width=True, key=f"{key_prefix}table_{i}")
    for i, c in enumerate(rendered.get("charts", [])):
        try:
            st.plotly_chart(go.Figure(c), use_container_width=True, key=f"{key_prefix}chart_{i}")
        except Exception as e:  # noqa: BLE001
            logger.exception("图表渲染失败")
            st.caption(f"图表渲染失败: {e}")


def run_question(question: str) -> None:
    # 构造对话历史（不含本轮），供 Agent 理解上文；assistant 提取 summary 文本
    history = []
    for m in st.session_state.messages:
        if m["role"] == "user":
            history.append({"role": "user", "content": m["content"]})
        else:
            content = m["content"]
            summary = content.get("summary") if isinstance(content, dict) else str(content)
            if summary:
                history.append({"role": "assistant", "content": str(summary)})
    with st.spinner("Agent 分析中..."):
        try:
            rendered = run_analysis(question, _get_llm(), history=history)
        except Exception as e:  # noqa: BLE001
            logger.exception("Agent 分析失败")
            rendered = {"summary": f"分析失败: {e}", "tables": [], "charts": []}
    st.session_state.messages.append({"role": "user", "content": question})
    st.session_state.messages.append({"role": "assistant", "content": rendered})


# ---------- 侧边栏 ----------
with st.sidebar:
    st.header("LangChain 数据分析 Agent")
    st.caption(f"模型: {settings.openai_model} | 端点: {settings.openai_base_url}")
    if not settings.openai_api_key and settings.openai_base_url == "https://api.openai.com/v1":
        st.warning("未配置 OPENAI_API_KEY，请在项目根目录 .env 中填写后重启。")
    st.divider()
    st.subheader("可用数据集")
    for meta in load_all_meta():
        with st.expander(f"[{meta['domain']}] {meta['title']}"):
            st.write(meta["description"])
            st.caption("字段: " + ", ".join(f["name"] for f in meta["fields"]))
    st.divider()
    st.subheader("示例问题")
    for q in EXAMPLES:
        if st.button(q, use_container_width=True):
            st.session_state.pending_query = q
            st.rerun()

# ---------- 主区域 ----------
st.title("数据分析 Agent")
st.caption("基于 LangGraph + Streamlit：自然语言提问 → 自动分析开源数据 → 表格 + 图表交付")

# 初始化 session_state（必须在 pending_query 之前）
if "messages" not in st.session_state:
    st.session_state.messages = []

# 处理待执行问题
if st.session_state.get("pending_query"):
    q = st.session_state.pop("pending_query")
    run_question(q)
    st.rerun()

# 渲染历史消息
for idx, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        if m["role"] == "assistant":
            render_result(m["content"], key_prefix=f"msg{idx}_")
        else:
            st.markdown(m["content"])

if prompt := st.chat_input("输入数据分析问题，例如：各国家销售额对比"):
    st.session_state.pending_query = prompt
    st.rerun()
