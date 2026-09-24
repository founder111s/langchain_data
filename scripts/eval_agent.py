"""Agent 评估脚本：用真实 LLM 跑标准问答集，量化 Agent 的表现。

评估维度：
- 一次通过率（是否正常交付 表格 + 图表）
- 平均工具调用轮数（用 rendered 中表格数代理）
- 失败原因采集

用法:
    python scripts/eval_agent.py                # 跑全部用例
    python scripts/eval_agent.py --sample 5     # 只跑前 5 条（快速验证）
    python scripts/eval_agent.py --report        # 生成评估报告 md
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import setup_logging  # noqa: E402

setup_logging()

# 启用 LangSmith 追踪（若配置了 API Key），使评估过程的每次 LLM/工具调用都可追溯
from app.llm import configure_langsmith  # noqa: E402

configure_langsmith()

# 标准问答集：5 个数据集 × 10 用例 = 50 条，覆盖 基础/全面/稳定 三维度
#  基础(basic)：预览、统计摘要、单字段分组/排序
#  全面(comprehensive)：多维分组、组合过滤、相关性/极值等深度分析
#  稳定(stable)：时间趋势、多组趋势对比、跨维度结合，验证 Agent 在常见场景下的稳定性
CASES = [
    # ========== 电商零售 ecommerce ==========
    {"q": "展示电商订单数据的前10条", "dataset": "ecommerce", "cat": "basic"},
    {"q": "各国家销售额对比", "dataset": "ecommerce", "cat": "comprehensive"},
    {"q": "电商每月总销售额趋势", "dataset": "ecommerce", "cat": "stable"},
    {"q": "销售额最高的5个国家", "dataset": "ecommerce", "cat": "comprehensive"},
    {"q": "英国的订单总销售额", "dataset": "ecommerce", "cat": "comprehensive"},
    {"q": "各国家销售的商品总数量对比", "dataset": "ecommerce", "cat": "comprehensive"},
    {"q": "电商订单的每日销售额趋势", "dataset": "ecommerce", "cat": "stable"},
    {"q": "德国的订单有哪些", "dataset": "ecommerce", "cat": "comprehensive"},
    {"q": "商品单价和销售额的统计摘要", "dataset": "ecommerce", "cat": "basic"},
    {"q": "各商品编码的总销售额排名前5", "dataset": "ecommerce", "cat": "comprehensive"},
    # ========== 金融股票 finance ==========
    {"q": "AAPL 近一年收盘价走势", "dataset": "finance", "cat": "stable"},
    {"q": "各股票的平均收盘价对比", "dataset": "finance", "cat": "comprehensive"},
    {"q": "各股票的平均成交量对比", "dataset": "finance", "cat": "comprehensive"},
    {"q": "AAPL 最近5个交易日的数据", "dataset": "finance", "cat": "comprehensive"},
    {"q": "各股票的最高收盘价", "dataset": "finance", "cat": "comprehensive"},
    {"q": "成交量最高的股票是哪个", "dataset": "finance", "cat": "comprehensive"},
    {"q": "TSLA 的收盘价时间趋势", "dataset": "finance", "cat": "stable"},
    {"q": "股票行情数据的统计摘要", "dataset": "finance", "cat": "basic"},
    {"q": "各股票的周平均收盘价对比", "dataset": "finance", "cat": "stable"},
    {"q": "某一天各股票的收盘价对比", "dataset": "finance", "cat": "comprehensive"},
    # ========== 银行风控 credit ==========
    {"q": "展示信用卡客户数据的前10条", "dataset": "credit", "cat": "basic"},
    {"q": "整体客户违约率是多少", "dataset": "credit", "cat": "basic"},
    {"q": "各教育程度违约率对比", "dataset": "credit", "cat": "comprehensive"},
    {"q": "男女客户的违约人数对比", "dataset": "credit", "cat": "comprehensive"},
    {"q": "各婚姻状况的违约率", "dataset": "credit", "cat": "comprehensive"},
    {"q": "不同信用额度区间的平均信用额度", "dataset": "credit", "cat": "comprehensive"},
    {"q": "客户的年龄统计摘要", "dataset": "credit", "cat": "basic"},
    {"q": "已婚客户和单身客户的违约率差异", "dataset": "credit", "cat": "comprehensive"},
    {"q": "信用额度最高的前5位客户", "dataset": "credit", "cat": "basic"},
    {"q": "研究生学历客户的账单金额top 5", "dataset": "credit", "cat": "basic"},
    # ========== 气候气象 climate ==========
    {"q": "北京的平均气温趋势", "dataset": "climate", "cat": "stable"},
    {"q": "各城市的平均最高气温对比", "dataset": "climate", "cat": "comprehensive"},
    {"q": "各城市的降水量总和对比", "dataset": "climate", "cat": "comprehensive"},
    {"q": "北京各月最高气温趋势", "dataset": "climate", "cat": "stable"},
    {"q": "各城市的最低气温统计", "dataset": "climate", "cat": "comprehensive"},
    {"q": "上海近一年的降水量趋势", "dataset": "climate", "cat": "stable"},
    {"q": "某一天四个城市的最高气温对比", "dataset": "climate", "cat": "comprehensive"},
    {"q": "各城市的平均最低气温对比", "dataset": "climate", "cat": "comprehensive"},
    {"q": "北京最高气温超过30度的记录", "dataset": "climate", "cat": "basic"},
    {"q": "气候数据的统计摘要", "dataset": "climate", "cat": "basic"},
    # ========== 公共卫生 health ==========
    {"q": "各国家累计确诊总数对比", "dataset": "health", "cat": "comprehensive"},
    {"q": "美国的新增确诊趋势", "dataset": "health", "cat": "stable"},
    {"q": "各国家累计死亡总数对比", "dataset": "health", "cat": "comprehensive"},
    {"q": "中国和英国的累计确诊对比", "dataset": "health", "cat": "comprehensive"},
    {"q": "各国家新增确诊的每日趋势对比", "dataset": "health", "cat": "stable"},
    {"q": "累计死亡最高的3个国家", "dataset": "health", "cat": "comprehensive"},
    {"q": "全球所有国家每日新增确诊趋势", "dataset": "health", "cat": "stable"},
    {"q": "美国的累计确诊是多少", "dataset": "health", "cat": "basic"},
    {"q": "健康数据的统计摘要", "dataset": "health", "cat": "basic"},
    {"q": "各国家每月的总确诊数对比", "dataset": "health", "cat": "stable"},
]


def run_eval(questions: list[dict]) -> list[dict]:
    from app.agent.graph import run_analysis
    from app.llm import get_llm

    llm = get_llm()
    results = []
    for i, case in enumerate(questions, 1):
        q, dataset = case["q"], case["dataset"]
        cat = case.get("cat", "-")
        start = time.time()
        error, summary, n_tables, n_charts = None, "", 0, 0
        try:
            rendered = run_analysis(q, llm)
            summary = (rendered.get("summary") or "").strip()
            n_tables = len(rendered.get("tables", []))
            n_charts = len(rendered.get("charts", []))
            if not n_tables:
                error = "无表格交付"
            elif cat != "basic" and not n_charts:
                # 基础类多为 head/describe，天然无图（chart_type=none），仅要求交付表格
                error = "无图表交付"
        except Exception as e:  # noqa: BLE001
            error = f"异常: {type(e).__name__}: {e}"
        elapsed = time.time() - start
        results.append({
            "id": i, "q": q, "dataset": dataset, "cat": cat,
            "pass": error is None, "error": error or "",
            "n_tables": n_tables, "n_charts": n_charts,
            "summary": summary, "elapsed_s": round(elapsed, 1),
        })
        status = "PASS" if error is None else "FAIL"
        print(f"[{status}] #{i} [{cat}] {dataset} | {error or f'{n_tables}表/{n_charts}图'} | {elapsed:.1f}s")
    return results


def summarize(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    avg_tables = sum(r["n_tables"] for r in results) / total if total else 0
    avg_charts = sum(r["n_charts"] for r in results) / total if total else 0
    by_dataset: dict[str, dict] = {}
    for r in results:
        d = by_dataset.setdefault(r["dataset"], {"total": 0, "pass": 0})
        d["total"] += 1
        d["pass"] += 1 if r["pass"] else 0
    by_cat: dict[str, dict] = {}
    for r in results:
        c = by_cat.setdefault(r["cat"], {"total": 0, "pass": 0})
        c["total"] += 1
        c["pass"] += 1 if r["pass"] else 0
    fail_reasons = [r["error"] for r in results if not r["pass"] and r["error"]]
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total * 100, 1) if total else 0,
        "avg_tables": round(avg_tables, 1),
        "avg_charts": round(avg_charts, 1),
        "by_dataset": by_dataset,
        "by_cat": by_cat,
        "fail_reasons": fail_reasons,
    }


def to_markdown(results: list[dict], stats: dict) -> str:
    lines = [
        "# Agent 评估报告",
        "",
        f"> 生成时间：`{time.strftime('%Y-%m-%d %H:%M:%S')}` ｜ 模型：环境配置（DeepSeek 兼容端点）",
        f"> 总用例 {stats['total']}，通过 {stats['passed']}，**一次通过率 {stats['pass_rate']}%**",
        f"> 平均每次交付表格 {stats['avg_tables']} 张、图表 {stats['avg_charts']} 张",
        "",
        "## 分数据集结果", "",
        "| 数据集 | 用例数 | 通过 | 通过率 |", "|---|---|---|---|",
    ]
    for name, d in sorted(stats["by_dataset"].items()):
        rate = round(d["pass"] / d["total"] * 100, 1) if d["total"] else 0
        lines.append(f"| {name} | {d['total']} | {d['pass']} | {rate}% |")
    lines += ["", "## 分维度结果", "", "| 维度 | 用例数 | 通过 | 通过率 |", "|---|---|---|---|"]
    cat_label = {"basic": "基础", "comprehensive": "全面", "stable": "稳定"}
    for name, d in stats["by_cat"].items():
        rate = round(d["pass"] / d["total"] * 100, 1) if d["total"] else 0
        lines.append(f"| {cat_label.get(name, name)} | {d['total']} | {d['pass']} | {rate}% |")
    lines += ["", "## 逐用例明细", "", "| # | 数据集 | 维度 | 问题 | 结果 | 表格 | 图表 | 耗时(s) |", "|---|---|---|---|---|---|---|---|"]
    for r in results:
        tag = "✅ 通过" if r["pass"] else "❌ 失败"
        lines.append(f"| {r['id']} | {r['dataset']} | {cat_label.get(r['cat'], r['cat'])} | {r['q']} | {tag} | {r['n_tables']} | {r['n_charts']} | {r['elapsed_s']} |")
    if stats["fail_reasons"]:
        lines += ["", "## 失败原因", ""]
        for reason in stats["fail_reasons"]:
            lines.append(f"- {reason}")
    return "\n".join(lines)


if __name__ == "__main__":
    cases = CASES
    if "--sample" in sys.argv:
        idx = sys.argv.index("--sample")
        n = int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else 5
        cases = CASES[:n]
    results = run_eval(cases)
    stats = summarize(results)
    print("\n===== 汇总 =====")
    print(f"通过率: {stats['pass_rate']}% ({stats['passed']}/{stats['total']})")
    print(f"平均表格数: {stats['avg_tables']}, 平均图表数: {stats['avg_charts']}")

    if "--report" in sys.argv:
        md = to_markdown(results, stats)
        out = ROOT / "docs" / "agent_eval_report.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"\n报告已写入: {out}")