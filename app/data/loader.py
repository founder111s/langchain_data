"""统一数据加载器：加载 app/data/raw 下的 CSV 为 DataFrame（带进程内缓存）。"""
import logging

import pandas as pd

from app.config import settings
from app.data.sources import DATASETS, DatasetSpec

logger = logging.getLogger(__name__)

_DF_CACHE: dict[str, pd.DataFrame] = {}


def _normalize(df: pd.DataFrame, spec: DatasetSpec) -> pd.DataFrame:
    df = df.copy()
    if spec.date_col and spec.date_col in df.columns:
        df[spec.date_col] = pd.to_datetime(df[spec.date_col], errors="coerce")
        df = df.dropna(subset=[spec.date_col])
    return df


def load_dataset(name: str) -> pd.DataFrame:
    """加载数据集（带缓存）。"""
    if name in _DF_CACHE:
        return _DF_CACHE[name]
    if name not in DATASETS:
        raise KeyError(f"未知数据集: {name}")
    spec = DATASETS[name]
    path = settings.data_dir / spec.file
    if not path.exists():
        raise FileNotFoundError(
            f"数据文件不存在: {path}。请先运行 python scripts/download_data.py 下载开源数据。"
        )
    df = pd.read_csv(path)
    df = _normalize(df, spec)
    _DF_CACHE[name] = df
    logger.info("已加载数据集 %s: %d 行 x %d 列", name, df.shape[0], df.shape[1])
    return df


def load_all_meta() -> list[dict]:
    return [spec.to_dict() for spec in DATASETS.values()]
