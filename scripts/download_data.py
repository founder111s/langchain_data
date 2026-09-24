"""下载 4 个领域开源数据集到 app/data/raw。

用法: python scripts/download_data.py [--force]
"""
import io
import json
import logging
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings, setup_logging  # noqa: E402

setup_logging()
logger = logging.getLogger("download_data")
DATA_DIR = settings.data_dir

UCI_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
# Online Retail：优先 GitHub 镜像（经 gh-proxy），回退 UCI 官网 ZIP
ECOMMERCE_CSV_URL = "https://gh-proxy.com/https://raw.githubusercontent.com/sheezanazeer98/Online-Retail-SQL/main/Online%20Retail.csv"
# OWID COVID-19：优先 GitHub 直连，国内网络回退 gh-proxy 镜像
OWID_URLS = [
    "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv",
    "https://gh-proxy.com/https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv",
]
CITIES = [
    {"city": "Beijing", "lat": 39.9042, "lon": 116.4074},
    {"city": "Shanghai", "lat": 31.2304, "lon": 121.4737},
    {"city": "New York", "lat": 40.7128, "lon": -74.0060},
    {"city": "London", "lat": 51.5074, "lon": -0.1278},
]
HEALTH_COUNTRIES = ["China", "United States", "India", "Germany", "Brazil", "Japan"]
# 腾讯行情接口（国内网络更稳定），代码为美股符号
TENCENT_TICKERS = {"AAPL": "usAAPL.OQ", "MSFT": "usMSFT.OQ", "GOOG": "usGOOG.OQ", "TSLA": "usTSLA.OQ"}
CLIMATE_START = "2024-09-11"
CLIMATE_END = "2026-09-11"
# UCI 信用卡违约数据集（Default of Credit Card Clients），银行风控经典数据
UCI_CREDIT_URL = "https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def _get(url: str, timeout: int = 180) -> requests.Response:
    logger.info("下载 %s", url)
    resp = requests.get(url, timeout=timeout, headers=_UA)
    resp.raise_for_status()
    return resp


def _skip(out: Path, force: bool) -> bool:
    if out.exists() and not force:
        logger.info("已存在 %s，跳过（--force 强制重下）", out.name)
        return True
    return False


def _parse_retail_bytes(raw: bytes) -> pd.DataFrame:
    """解析 Online Retail 数据：自动识别 XLSX / ZIP / CSV 格式。"""
    if raw[:2] == b"PK":
        # 先按 XLSX 直接读取（xlsx 本身是 ZIP 结构）
        try:
            return pd.read_excel(io.BytesIO(raw))
        except Exception:  # noqa: BLE001
            pass
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            csv_name = next((n for n in names if n.lower().endswith(".csv")), None)
            xlsx_name = next((n for n in names if n.lower().endswith(".xlsx")), None)
            if csv_name:
                data = zf.read(csv_name)
                try:
                    return pd.read_csv(io.BytesIO(data))
                except UnicodeDecodeError:
                    return pd.read_csv(io.BytesIO(data), encoding="latin-1")
            if xlsx_name:
                return pd.read_excel(zf.open(xlsx_name))
            raise RuntimeError(f"ZIP 中未找到 CSV/XLSX: {names}")
    try:
        return pd.read_csv(io.BytesIO(raw))
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(raw), encoding="latin-1")


def download_ecommerce(force: bool) -> None:
    """Online Retail（UCI）在线零售订单数据，多源回退。"""
    out = DATA_DIR / "ecommerce_retail.csv"
    if _skip(out, force):
        return
    df = None
    errors = []
    for url in (ECOMMERCE_CSV_URL, UCI_URL):
        try:
            df = _parse_retail_bytes(_get(url).content)
            if df is not None and len(df):
                logger.info("电商数据源可用: %s", url)
                break
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url} 失败: {e}")
            df = None
    if df is None:
        raise RuntimeError("电商数据全部数据源失败: " + "; ".join(errors))
    df.columns = [str(c).strip() for c in df.columns]
    if "Revenue" not in df.columns and "Quantity" in df.columns and "UnitPrice" in df.columns:
        df["Revenue"] = pd.to_numeric(df["Quantity"], errors="coerce") * pd.to_numeric(
            df["UnitPrice"], errors="coerce"
        )
    keep = [c for c in ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country", "Revenue"] if c in df.columns]
    df = df[keep].dropna(subset=["InvoiceDate"])
    df.to_csv(out, index=False)
    logger.info("电商零售: %d 行 -> %s", len(df), out)


def download_finance(force: bool) -> None:
    """腾讯行情接口拉取美股日线（含前复权）。"""
    out = DATA_DIR / "finance_daily.csv"
    if _skip(out, force):
        return
    end = date.today()
    start = end - timedelta(days=400)
    frames = []
    for tk, code in TENCENT_TICKERS.items():
        url = (
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            f"?param={code},day,{start.isoformat()},{end.isoformat()},320,qfq"
        )
        try:
            payload = _get(url, timeout=60).json()
        except Exception as e:  # noqa: BLE001
            logger.warning("%s 行情获取失败: %s", tk, e)
            continue
        node = payload.get("data", {}).get(code) or payload.get("data", {}).get(tk) or {}
        arr = node.get("qfqday") or node.get("day") or []
        if not arr:
            logger.warning("未获取到 %s 行情", tk)
            continue
        d = pd.DataFrame(arr).iloc[:, :6]
        d.columns = ["Date", "Open", "Close", "High", "Low", "Volume"]
        d["Ticker"] = tk
        frames.append(d)
    if not frames:
        raise RuntimeError("腾讯行情未返回任何数据")
    df = pd.concat(frames, ignore_index=True)
    for c in ["Open", "Close", "High", "Low", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.to_csv(out, index=False)
    logger.info("金融股票: %d 行 -> %s", len(df), out)


def download_climate(force: bool) -> None:
    """Open-Meteo 历史气象档案（城市日值）。"""
    out = DATA_DIR / "climate_cities.csv"
    if _skip(out, force):
        return
    frames = []
    for city in CITIES:
        url = (
            "https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={city['lat']}&longitude={city['lon']}"
            f"&start_date={CLIMATE_START}&end_date={CLIMATE_END}"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
        )
        daily = _get(url).json().get("daily", {})
        d = pd.DataFrame(daily)
        d["City"] = city["city"]
        frames.append(d)
    df = pd.concat(frames, ignore_index=True).rename(
        columns={
            "time": "Date",
            "temperature_2m_max": "tmax",
            "temperature_2m_min": "tmin",
            "precipitation_sum": "precipitation",
        }
    )
    df.to_csv(out, index=False)
    logger.info("气候气象: %d 行 -> %s", len(df), out)


def download_health(force: bool) -> None:
    """Our World in Data COVID-19 数据（部分国家子集，多源回退）。"""
    out = DATA_DIR / "covid_owid.csv"
    if _skip(out, force):
        return
    content = None
    for url in OWID_URLS:
        try:
            content = _get(url).content
            logger.info("健康数据源可用: %s", url)
            break
        except Exception as e:  # noqa: BLE001
            logger.warning("健康数据源 %s 失败: %s", url, e)
    if content is None:
        raise RuntimeError("所有健康数据源均不可用")
    df = pd.read_csv(io.BytesIO(content))
    keep = [c for c in ["date", "location", "total_cases", "new_cases", "total_deaths", "new_deaths"] if c in df.columns]
    df = df[keep]
    df = df[df["location"].isin(HEALTH_COUNTRIES)].dropna(subset=["date"])
    df.to_csv(out, index=False)
    logger.info("公共卫生: %d 行 -> %s", len(df), out)


def download_credit(force: bool) -> None:
    """UCI 信用卡违约数据集（Default of Credit Card Clients），银行风控经典数据。"""
    out = DATA_DIR / "credit_default.csv"
    if _skip(out, force):
        return
    raw = _get(UCI_CREDIT_URL).content
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            xls_name = next((n for n in zf.namelist() if n.lower().endswith(".xls")), None)
            if not xls_name:
                raise RuntimeError(f"ZIP 中未找到 XLS: {zf.namelist()}")
            raw = zf.read(xls_name)
    # .xls 第一行是说明，第二行才是表头
    df = pd.read_excel(io.BytesIO(raw), header=1)
    df.columns = [str(c).strip() for c in df.columns]
    # 违约标签列名含空格，重命名便于分析
    df = df.rename(columns={"default payment next month": "DEFAULT"})
    keep = [
        "ID", "LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE",
        "PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6",
        "BILL_AMT1", "BILL_AMT2", "BILL_AMT3", "BILL_AMT4", "BILL_AMT5", "BILL_AMT6",
        "PAY_AMT1", "PAY_AMT2", "PAY_AMT3", "PAY_AMT4", "PAY_AMT5", "PAY_AMT6",
        "DEFAULT",
    ]
    keep = [c for c in keep if c in df.columns]
    df = df[keep]
    df.to_csv(out, index=False)
    logger.info("信用卡违约: %d 行 -> %s", len(df), out)


def main() -> None:
    force = "--force" in sys.argv
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / ".gitkeep").touch(exist_ok=True)
    results = {}
    for task in (download_ecommerce, download_finance, download_climate, download_health, download_credit):
        try:
            task(force)
            results[task.__name__] = "OK"
        except Exception as e:  # noqa: BLE001
            logger.error("%s 失败: %s", task.__name__, e)
            results[task.__name__] = f"FAIL: {e}"
    logger.info("下载结果: %s", json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
