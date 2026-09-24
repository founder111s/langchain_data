# LangChain 数据分析 Agent

基于 LangChain + LangGraph 的多领域数据分析 Agent：用户用自然语言提问，Agent 自动选择开源数据集、执行统计分析，最终以**表格 + 图表**形式在 Streamlit 网站上交付。

## 功能特性

- **LangGraph 有状态编排**：`router → analyze → output` 节点图，工具调用循环直至交付
- **4 个领域开源数据**：电商零售（UCI Online Retail）、金融股票（腾讯行情）、气候气象（Open-Meteo）、公共卫生（OWID COVID-19）
- **统一表格交付**：所有分析结果规范化为 `tables[]`（标题/列/行），由输出节点自动生成对应 Plotly 图表
- **安全分析**：白名单 Pandas 操作（分组聚合/时间趋势/过滤/相关性），不执行任意代码
- **可部署**：配置全部外部化（`.env`），Docker / docker-compose 一键启动

## 项目结构

```
├── app/
│   ├── streamlit_app.py        # 网站入口：对话 + 表格/图表渲染
│   ├── config.py               # 配置（.env 外部化）
│   ├── llm.py                  # OpenAI 兼容 LLM 工厂
│   ├── agent/                  # LangGraph 图编排（state/prompts/nodes/graph）
│   ├── tools/                  # 工具层（数据/分析/表格/图表）
│   └── data/                   # 数据集定义与统一加载
│       └── raw/                # 开源原始数据（下载生成）
├── scripts/
│   ├── download_data.py        # 下载 4 领域开源数据
│   └── smoke_test.py           # 冒烟测试
├── Dockerfile / docker-compose.yml
└── requirements.txt
```

## 快速开始

```bash
# 1. 配置 LLM（OpenAI 兼容接口，支持 DeepSeek / Qwen / OpenAI / vLLM 等）
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL

# 2. 安装依赖（建议虚拟环境）
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 3. 下载开源数据（约需几分钟，视网络而定）
python scripts/download_data.py

# 4. 冒烟测试（验证数据/工具/图表/图编排，无需 LLM）
python scripts/smoke_test.py

# 5. 启动网站
streamlit run app/streamlit_app.py
# 浏览器访问 http://localhost:8501
```

## Docker 部署

```bash
cp .env.example .env   # 先配置好 .env
docker compose up -d --build
# 访问 http://localhost:8501
```

## 示例问题

| 领域 | 问题 |
|------|------|
| 电商零售 | 各国家销售额对比；电商每月销售额趋势 |
| 金融股票 | AAPL 收盘价走势；各股票平均收盘价对比；各股票收盘价相关性 |
| 气候气象 | 各城市月平均最高温对比；北京近一年平均气温趋势 |
| 公共卫生 | 各国每月新增确诊对比 |

## 配置说明（.env）

| 变量 | 说明 | 示例 |
|------|------|------|
| OPENAI_API_KEY | OpenAI 兼容接口 Key | sk-xxx |
| OPENAI_BASE_URL | API 端点 | https://api.deepseek.com/v1 |
| OPENAI_MODEL | 模型名 | deepseek-chat / gpt-4o-mini |
| DATA_DIR | 数据目录（留空用默认） | |
| LOG_LEVEL | 日志级别 | INFO |

## Agent 工作流程

```
用户提问
  → list_datasets（了解可用数据集）
  → select_dataset（可选，预览字段）
  → analyze_data（白名单统计分析，返回 TableResult JSON）
  → deliver（交付 summary + tables，结束循环）
  → output 节点（自动生成 Plotly 图表）
  → Streamlit 渲染表格 + 图表
```
